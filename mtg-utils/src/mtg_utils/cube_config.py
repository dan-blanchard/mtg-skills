"""Cube format configuration and design-target constants."""

from __future__ import annotations

# ── Cube format presets ──
#
# Unlike deck formats, most cube rules are soft — a user can ignore defaults
# and build any card pool they want. These entries provide sensible starting
# points for size, rarity filtering, and legality gating.
#
# Keys:
#   default_size       — typical cube size for the format
#   rarity_filter      — set of Scryfall rarities allowed in the main pool,
#                        or None for no filter
#   commander_pool_rarity_filter — same for the commander pool (PDH uses
#                        uncommons for commanders but commons for main)
#   legality_key       — Scryfall `legalities[<key>]` to gate cards against,
#                        or None for no legality gate
#   has_commander_pool — whether this format drafts from a separate pool of
#                        legendary creatures
#   ban_list           — names of cards explicitly banned from the pool
CUBE_FORMAT_CONFIGS: dict[str, dict] = {
    "vintage": {
        "default_size": 540,
        "rarity_filter": None,
        "commander_pool_rarity_filter": None,
        "legality_key": None,
        "has_commander_pool": False,
        "ban_list": [],
    },
    "unpowered": {
        "default_size": 540,
        "rarity_filter": None,
        "commander_pool_rarity_filter": None,
        "legality_key": None,
        "has_commander_pool": False,
        # Conventional "unpowered" ban list — the Power 9.
        "ban_list": [
            "Black Lotus",
            "Mox Sapphire",
            "Mox Jet",
            "Mox Pearl",
            "Mox Ruby",
            "Mox Emerald",
            "Ancestral Recall",
            "Time Walk",
            "Timetwister",
        ],
    },
    "legacy": {
        "default_size": 540,
        "rarity_filter": None,
        "commander_pool_rarity_filter": None,
        "legality_key": "legacy",
        "has_commander_pool": False,
        "ban_list": [],
    },
    "modern": {
        "default_size": 540,
        "rarity_filter": None,
        "commander_pool_rarity_filter": None,
        "legality_key": "modern",
        "has_commander_pool": False,
        "ban_list": [],
    },
    "pauper": {
        "default_size": 540,
        "rarity_filter": frozenset({"common"}),
        "commander_pool_rarity_filter": None,
        "legality_key": None,
        "has_commander_pool": False,
        "ban_list": [],
    },
    "peasant": {
        "default_size": 540,
        "rarity_filter": frozenset({"common", "uncommon"}),
        "commander_pool_rarity_filter": None,
        "legality_key": None,
        "has_commander_pool": False,
        "ban_list": [],
    },
    "set": {
        "default_size": 360,
        "rarity_filter": None,
        "commander_pool_rarity_filter": None,
        "legality_key": None,
        "has_commander_pool": False,
        "ban_list": [],
    },
    "commander": {
        "default_size": 540,
        "rarity_filter": None,
        "commander_pool_rarity_filter": None,
        "legality_key": "commander",
        "has_commander_pool": True,
        "ban_list": [],
    },
    "pdh": {
        "default_size": 540,
        # PDH main pool: commons only.
        "rarity_filter": frozenset({"common"}),
        # PDH commanders: uncommon creatures (traditionally).
        "commander_pool_rarity_filter": frozenset({"uncommon"}),
        "legality_key": None,
        "has_commander_pool": True,
        "ban_list": [],
    },
}


# ── Cube size to drafter count ──
#
# Conventional guideline: 360 cards supports 8 drafters, 45 cards per seat
# thereafter. From Lucky Paper's Cube FAQ.
SIZE_TO_DRAFTERS: dict[int, int] = {
    360: 8,
    450: 10,
    540: 12,
    630: 14,
    720: 16,
}


# ── Pack templates ──
#
# Slot allocations for seeded pack generation, ported from cube-utils.
# Categories are the same 9 used by classify_cube_category():
#   W / U / B / R / G — mono-color
#   M — multicolor
#   L — land that produces at most one color
#   F — fixing land (produces two or more colors — dual lands, triomes,
#       on-color fetches, any-color sources)
#   C — colorless non-land (includes mana rocks; they draft out of the
#       colorless slot, not a dedicated fixing slot)
#
# "extra_mono" slots are distributed randomly among the five mono colors
# when the pack is built.
PACK_TEMPLATES: dict[int, dict[str, int]] = {
    9: {
        "W": 1,
        "U": 1,
        "B": 1,
        "R": 1,
        "G": 1,
        "M": 1,
        "F": 1,
        "extra_mono": 2,
    },
    11: {
        "W": 1,
        "U": 1,
        "B": 1,
        "R": 1,
        "G": 1,
        "M": 1,
        "L": 1,
        "F": 1,
        "extra_mono": 3,
    },
    15: {
        "W": 1,
        "U": 1,
        "B": 1,
        "R": 1,
        "G": 1,
        "M": 1,
        "L": 1,
        "F": 1,
        "C": 1,
        "extra_mono": 6,
    },
}


# ── Balance reference ranges (informational, NOT pass/fail gates) ──
#
# These are typical ranges observed across well-balanced cubes. A cube that
# falls outside these ranges isn't broken — it might be an intentional
# design choice (mono-color cube, combo cube, etc.). `cube-balance` reports
# the observed value alongside the reference range as context.
BALANCE_TARGETS: dict[str, object] = {
    # Per-color count tolerance: within ±5% of the mean of present colors.
    "color_balance_pct_tolerance": 5.0,
    # Removal as a fraction of nonland cards (Riptide Lab consensus range).
    "removal_density_pct": (22.0, 28.0),
    # Lucky Paper "How Many Lands" fixing bands at 360 cube size.
    # Fixing density below 17% is under-supported; 17-28% is the optimal band.
    "fixing_density_pct": (17.0, 28.0),
    # Fixing-maindeck-efficiency curve: observed maindeck rate (%) at a given
    # fixing density (% of cube). Linear interpolation between points.
    "fixing_maindeck_efficiency": {
        5.0: 62.8,
        10.0: 67.3,
        13.0: 77.0,
    },
    # Minimum card count for an archetype to be draftable (LP FAQ).
    "min_archetype_signal_density": 3,
    # Warn threshold for archetype density (informational "thin" signal).
    "warn_archetype_signal_density": 5,
}


# ── Reference cubes ──
#
# Each entry is a list of candidate "starting-point" cubes for a given format.
# IDs are CubeCobra short IDs — fetch one with:
#   cubecobra-fetch <id> --output-dir <dir>
# Sizes are approximate; always confirm against the live fetch. Entries are
# curated from community-known cubes; users can always paste any CubeCobra URL
# instead of picking from this list.
REFERENCE_CUBES: dict[str, list[dict[str, str | int]]] = {
    "vintage": [
        {
            "id": "modovintage",
            "name": "MTGO Vintage Cube",
            "description": "WotC's canonical powered vintage cube on MTGO, updated seasonally",
            "size": 540,
        },
        {
            "id": "cbvc",
            "name": "CB Vintage Cube",
            "description": "Caleb Gannon's curated 540 powered vintage cube",
            "size": 540,
        },
        {
            "id": "qiv",
            "name": "Big Vintage Cube",
            "description": "720-card powered vintage cube with broader archetype support",
            "size": 720,
        },
        {
            "id": "MaxPower360",
            "name": "Max Power - 360",
            "description": "Small powered vintage cube focused on individual card power",
            "size": 360,
        },
        {
            "id": "hp360",
            "name": "HP Vintage 360",
            "description": "Highly-powered 360 vintage cube with Storm and Shops archetypes",
            "size": 360,
        },
    ],
    "unpowered": [
        {
            "id": "hur",
            "name": "Unpowered Cube",
            "description": "Well-established 540 unpowered eternal cube",
            "size": 540,
        },
        {
            "id": "27x",
            "name": "540 Unpowered Cube",
            "description": "Classic community unpowered 540 vintage cube",
            "size": 540,
        },
    ],
    "legacy": [
        {
            "id": "olympiad",
            "name": "Legacy Cube",
            "description": "High-power legacy-legal cube organized around guild identity",
            "size": 540,
        },
        {
            "id": "3f7ml",
            "name": "Mostly Legacy Cube",
            "description": "540-card legacy-legal cube with balance-focused additions",
            "size": 540,
        },
        {
            "id": "1o0",
            "name": "Big Legacy Cube",
            "description": "540 cards built as a 360 base plus a 180-card legacy extension",
            "size": 540,
        },
    ],
    "modern": [
        {
            "id": "modomodern",
            "name": "MTGO Modern Cube",
            "description": "WotC's canonical 540-card modern-legal cube on MTGO",
            "size": 540,
        },
    ],
    "pauper": [
        {
            "id": "thepaupercube",
            "name": "The Pauper Cube",
            "description": "Canonical commons-only cube (thepaupercube.com)",
            "size": 450,
        },
    ],
    "peasant": [
        {
            "id": "sammich_peasant",
            "name": "Sammich's Peasant Cube",
            "description": "450-card peasant legacy cube (commons + uncommons)",
            "size": 450,
        },
        {
            "id": "shandoral",
            "name": "Peasant Power 450",
            "description": "Power-forward peasant cube using only commons and uncommons",
            "size": 450,
        },
        {
            "id": "thepeasantcube",
            "name": "The Peasant Cube",
            "description": "Community-maintained peasant cube with archetype support",
            "size": 450,
        },
    ],
    "set": [
        {
            "id": "duskmournsetcube",
            "name": "Duskmourn Set Cube",
            "description": "Single-set cube tuned for 8-player drafts",
            "size": 360,
        },
        {
            "id": "spoopycube",
            "name": "The Innistrad Remastered Cube",
            "description": "Gothic-horror themed single-block set cube",
            "size": 540,
        },
    ],
    "commander": [
        {
            "id": "ben_cube",
            "name": "The Compendious Commander Cube",
            "description": "Widely referenced commander cube with a dedicated commander pool",
            "size": 540,
        },
        {
            "id": "commandercube",
            "name": "Commander Cube",
            "description": "8-player commander cube using 4-pack drafts with a separate pool",
            "size": 540,
        },
        {
            "id": "mahjscommandercube",
            "name": "Easy-To-Understand Commander Cube",
            "description": "480 main cards plus a dedicated 90-card commander pool",
            "size": 570,
        },
    ],
    "pdh": [
        {
            "id": "w4z2",
            "name": "Pauper EDH Cube",
            "description": "pEDH cube where commanders are uncommons and the 99 are commons",
            "size": 540,
        },
        {
            "id": "chanspauperedh",
            "name": "Chan's Pauper EDH",
            "description": "PDH cube with commander-drafting mechanics",
            "size": 540,
        },
        {
            "id": "PDHLegends",
            "name": "Pauper EDH Legends",
            "description": "PDH variant requiring legendary commanders (including commons)",
            "size": 540,
        },
    ],
}


def get_cube_config(cube_json: dict) -> dict:
    """Return cube config for a cube JSON, with target_size override support.

    Reads 'cube_format' from cube_json (default: 'vintage').
    If cube_json contains an explicit 'target_size', overrides the config default.
    Raises ValueError for unknown format names.
    """
    fmt = cube_json.get("cube_format", "vintage")
    if fmt not in CUBE_FORMAT_CONFIGS:
        valid = ", ".join(sorted(CUBE_FORMAT_CONFIGS))
        msg = f"Unknown cube format: {fmt!r}. Valid formats: {valid}"
        raise ValueError(msg)
    cfg = dict(CUBE_FORMAT_CONFIGS[fmt])
    if "target_size" in cube_json:
        cfg["default_size"] = cube_json["target_size"]
    return cfg


def get_pack_templates(cube_json: dict) -> dict[int, dict[str, int]]:
    """Return pack templates for a cube, overridable via cube_json['pack_templates']."""
    override = cube_json.get("pack_templates")
    if not override:
        return PACK_TEMPLATES
    # Merge override into defaults: override wins per-size.
    merged = {int(k): v for k, v in override.items()}
    return {**PACK_TEMPLATES, **merged}


def get_balance_targets(cube_json: dict) -> dict[str, object]:
    """Return balance targets, overridable via cube_json['balance_targets_override']."""
    override = cube_json.get("balance_targets_override") or {}
    return {**BALANCE_TARGETS, **override}


def drafters_for_size(target_size: int) -> int:
    """Return conventional drafter count for a cube size.

    Falls back to 360 baseline + 1 drafter per 45 extra cards for
    non-canonical sizes. From Lucky Paper's Cube FAQ.
    """
    if target_size in SIZE_TO_DRAFTERS:
        return SIZE_TO_DRAFTERS[target_size]
    if target_size < 360:
        return 8
    return 8 + (target_size - 360) // 45
