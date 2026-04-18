"""Cross-reference theme queries against color pairs in a cube.

Each theme is a user-supplied oracle-text regex (e.g.
``tokens=create .* creature token``). The tool runs each regex against the
hydrated cube, groups matches by color pair, and reports per-theme density.
This replaces the need for a hardcoded guild/theme map — the user supplies
the intent, the tool validates whether the cube has support for it.

See Lucky Paper's FAQ: an archetype "needs as little as 3-4 cards" — themes
below the configured minimum get a warning note.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import (
    build_card_lookup,
    get_oracle_text,
    is_land,
)
from mtg_utils.cube_config import get_balance_targets

# The ten conventional two-color "guild" pairs. We compute per-guild theme
# density even without a guild NAME map — drafters organize around color
# pairs regardless of what the designer calls them.
GUILD_PAIRS = [
    frozenset({"W", "U"}),
    frozenset({"U", "B"}),
    frozenset({"B", "R"}),
    frozenset({"R", "G"}),
    frozenset({"W", "G"}),
    frozenset({"W", "B"}),
    frozenset({"U", "R"}),
    frozenset({"B", "G"}),
    frozenset({"R", "W"}),
    frozenset({"G", "U"}),
]


def _guild_label(pair: frozenset[str]) -> str:
    """Sorted two-letter label ("WU", "BR", ...) for a color pair."""
    return "".join(sorted(pair))


def _parse_theme_flag(raw: str) -> tuple[str, re.Pattern]:
    """Parse a ``name=regex`` CLI flag into (name, compiled regex)."""
    if "=" not in raw:
        msg = (
            f"Theme spec {raw!r} must be 'name=regex' "
            "(e.g. 'tokens=create .* creature token')"
        )
        raise click.BadParameter(msg)
    name, regex = raw.split("=", 1)
    name = name.strip()
    regex = regex.strip()
    if not name or not regex:
        raise click.BadParameter(f"Theme spec {raw!r} has empty name or regex")
    try:
        pattern = re.compile(regex, re.IGNORECASE)
    except re.error as exc:
        raise click.BadParameter(f"Invalid regex in {raw!r}: {exc}") from exc
    return name, pattern


def _color_pair_label_for_card(card: dict) -> str:
    """Categorize a card's color identity for archetype bucketing."""
    identity = card.get("color_identity", []) or []
    if not identity:
        return "Colorless"
    if len(identity) == 1:
        return identity[0]
    if len(identity) == 2:
        return _guild_label(frozenset(identity))
    return "".join(sorted(identity))  # 3+ colors, shown as "WUB" etc.


def _card_supports_guild(card: dict, pair: frozenset[str]) -> bool:
    """A card supports a guild pair if its color identity is a subset of that pair.

    Colorless cards (no color identity) also support every pair — they're
    splashable into any archetype.
    """
    identity = set(card.get("color_identity", []) or [])
    if not identity:
        return True
    return identity.issubset(pair)


def archetype_audit(
    cube: dict,
    hydrated: list[dict],
    themes: dict[str, re.Pattern],
    *,
    min_density: int | None = None,
) -> dict:
    lookup = build_card_lookup(hydrated)
    targets = get_balance_targets(cube)
    threshold = min_density or int(targets.get("min_archetype_signal_density", 3))
    warn_threshold = int(targets.get("warn_archetype_signal_density", 5))

    # Build: per-theme list of matching cards (with color identity info).
    per_theme: dict[str, dict] = {}
    for theme_name, pattern in themes.items():
        matches: list[dict] = []
        for entry in cube.get("cards", []):
            card = lookup.get(entry["name"])
            if card is None:
                continue
            if is_land(card):
                continue
            oracle = get_oracle_text(card)
            if not pattern.search(oracle):
                continue
            matches.append(
                {
                    "name": entry["name"],
                    "quantity": int(entry.get("quantity", 1)),
                    "color_identity": card.get("color_identity", []) or [],
                    "type_line": card.get("type_line", ""),
                }
            )

        total = sum(m["quantity"] for m in matches)

        by_color_pair: dict[str, int] = {}
        for m in matches:
            label = _color_pair_label_for_card(m)
            by_color_pair[label] = by_color_pair.get(label, 0) + m["quantity"]

        by_guild: dict[str, int] = {}
        for pair in GUILD_PAIRS:
            count = sum(m["quantity"] for m in matches if _card_supports_guild(m, pair))
            if count:
                by_guild[_guild_label(pair)] = count

        notes: list[str] = []
        if total < threshold:
            notes.append(
                f"only {total} cards support this theme — below LP minimum of "
                f"{threshold}; archetype may not be draftable"
            )
        elif total < warn_threshold:
            notes.append(
                f"{total} cards support this theme — thin by conventional "
                f"standards (warn threshold {warn_threshold})"
            )

        # Orphan signal: theme has support in only one mono-color.
        mono_supports = {
            color: by_color_pair.get(color, 0)
            for color in ("W", "U", "B", "R", "G")
            if by_color_pair.get(color, 0) > 0
        }
        if len(mono_supports) == 1 and not by_guild:
            (lone_color,) = mono_supports
            notes.append(
                f"orphan signal: theme appears only in mono-{lone_color} cards"
            )

        per_theme[theme_name] = {
            "total": total,
            "by_color_pair": by_color_pair,
            "by_guild": by_guild,
            "cards": [m["name"] for m in matches],
            "notes": notes,
        }

    # Bridge cards: appear in >=2 themes.
    bridge_counter: dict[str, list[str]] = {}
    for theme_name, info in per_theme.items():
        for name in info["cards"]:
            bridge_counter.setdefault(name, []).append(theme_name)
    bridges = sorted(
        (
            {"name": name, "themes": themes_list, "theme_count": len(themes_list)}
            for name, themes_list in bridge_counter.items()
            if len(themes_list) >= 2
        ),
        key=lambda x: (-x["theme_count"], x["name"]),
    )

    return {
        "themes": per_theme,
        "bridge_cards": bridges,
        "min_density_threshold": threshold,
        "warn_density_threshold": warn_threshold,
    }


def render_text_report(audit: dict) -> str:
    lines: list[str] = []
    themes = audit.get("themes", {})
    lines.append(f"archetype-audit: {len(themes)} theme(s)")
    lines.append("")
    for name, info in themes.items():
        lines.append(f"[{name}] {info['total']} card(s)")
        by_guild = info.get("by_guild") or {}
        if by_guild:
            parts = [
                f"{k}:{v}" for k, v in sorted(by_guild.items(), key=lambda x: -x[1])
            ]
            lines.append("  by guild: " + ", ".join(parts))
        by_pair = info.get("by_color_pair") or {}
        mono_parts = [
            f"{k}:{by_pair[k]}" for k in ("W", "U", "B", "R", "G") if k in by_pair
        ]
        if mono_parts:
            lines.append("  mono: " + ", ".join(mono_parts))
        for note in info.get("notes", []) or []:
            lines.append(f"  · {note}")
        lines.append("")

    bridges = audit.get("bridge_cards") or []
    if bridges:
        lines.append(f"Bridge cards ({len(bridges)}):")
        for b in bridges[:10]:
            lines.append(f"  {b['name']} — {', '.join(b['themes'])}")
        if len(bridges) > 10:
            lines.append(f"  ... and {len(bridges) - 10} more")
    else:
        lines.append("No bridge cards (no card matches ≥2 themes)")

    return "\n".join(lines) + "\n"


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--theme",
    "theme_specs",
    multiple=True,
    help="Theme definition 'name=regex'. Repeatable. Uses Python regex syntax.",
)
@click.option(
    "--from-cube",
    is_flag=True,
    default=False,
    help="Read theme names from cube_json.designer_intent.stated_archetypes. "
    "Names without an oracle regex are skipped with a warning.",
)
@click.option(
    "--min-density",
    type=int,
    default=None,
    help="Override minimum card count before a theme gets a warning note.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
@click.option(
    "--json",
    "emit_json",
    is_flag=True,
    default=False,
    help="Emit JSON envelope to stdout.",
)
def main(
    cube_path: Path,
    hydrated_path: Path,
    theme_specs: tuple[str, ...],
    min_density: int | None,
    output_path: Path | None,
    *,
    from_cube: bool,
    emit_json: bool,
):
    """Cross-reference user-supplied theme regexes against color pairs in a cube."""
    cube_content = cube_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    cube = json.loads(cube_content)
    hydrated = json.loads(hydrated_content)

    themes: dict[str, re.Pattern] = {}
    skipped_names: list[str] = []

    if from_cube:
        stated = (cube.get("designer_intent") or {}).get("stated_archetypes") or []
        for entry in stated:
            if isinstance(entry, dict) and entry.get("regex"):
                name = entry.get("name") or entry["regex"]
                themes[name] = re.compile(entry["regex"], re.IGNORECASE)
            elif isinstance(entry, str):
                skipped_names.append(entry)
        if skipped_names:
            click.echo(
                f"WARNING: {len(skipped_names)} stated archetype(s) without regex "
                "skipped: " + ", ".join(skipped_names),
                err=True,
            )

    for spec in theme_specs:
        name, pattern = _parse_theme_flag(spec)
        themes[name] = pattern

    if not themes:
        raise click.UsageError(
            "No themes specified. Pass --theme name=regex (repeatable) "
            "or --from-cube if the cube JSON lists them."
        )

    result = archetype_audit(cube, hydrated, themes, min_density=min_density)

    if output_path is None:
        theme_key = ",".join(sorted(themes.keys()))
        output_path = sha_keyed_path(
            "archetype-audit", cube_content, hydrated_content, theme_key
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    if emit_json:
        click.echo(json.dumps(result, indent=2))
        click.echo(f"Full JSON: {output_path}")
    else:
        click.echo(render_text_report(result), nl=False)
        click.echo(f"\nFull JSON: {output_path}")
