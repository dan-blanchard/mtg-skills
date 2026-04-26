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
    is_land,
)
from mtg_utils.cube_config import get_balance_targets
from mtg_utils.theme_presets import (
    PRESETS,
    Preset,
    get_preset,
    list_presets,
)

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


def _parse_theme_flag(raw: str) -> tuple[str, Preset]:
    """Parse a ``name=regex`` CLI flag into a (name, custom Preset) pair.

    The returned Preset has no keyword bindings and no test fixtures — it's
    a wrapper around the user-supplied regex so the audit loop can treat
    custom themes and library presets uniformly.
    """
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
    preset = Preset(
        name=name,
        description=f"custom --theme regex: {regex}",
        patterns=(pattern,),
    )
    return name, preset


def _resolve_preset_flag(raw: str) -> tuple[str, Preset]:
    """Look up ``--preset <name>`` in the registry. Raises on unknown name."""
    name = raw.strip()
    if not name:
        raise click.BadParameter("--preset value cannot be empty")
    try:
        preset = get_preset(name)
    except KeyError:
        known = ", ".join(sorted(PRESETS.keys()))
        raise click.BadParameter(
            f"unknown preset {name!r}. Known presets: {known}"
        ) from None
    return name, preset


# MTG creature types with irregular English plurals. Regular types
# (Goblin/Goblins, Zombie/Zombies, Wizard/Wizards) get an "s" suffix by
# default — this map only needs to cover the exceptions. Merfolk is its
# own plural and is handled by the fallback (no pluralization added).
_KINDRED_IRREGULAR_PLURALS = {
    "elf": "elves",
    "dwarf": "dwarves",
    "wolf": "wolves",
    "werewolf": "werewolves",
    "thief": "thieves",
    "leaf": "leaves",
    "merfolk": "merfolk",
    "fish": "fish",
    "sheep": "sheep",
}


def _parse_rewrite_flag(raw: str) -> tuple[str, str]:
    """Parse a ``source -> dest`` rewrite rule.

    Both names are stripped. Returns ``(source_theme, dest_theme)``. The
    caller is responsible for confirming both names resolve to themes
    defined in the current invocation.
    """
    if "->" not in raw:
        msg = (
            f"Rewrite rule {raw!r} must be 'source -> dest' "
            "(e.g. 'kindred-elf -> drain')"
        )
        raise click.BadParameter(msg)
    source, _, dest = raw.partition("->")
    source = source.strip()
    dest = dest.strip()
    if not source or not dest:
        raise click.BadParameter(f"Rewrite rule {raw!r} has empty source or dest")
    return source, dest


def _build_kindred_preset(creature_type: str) -> tuple[str, Preset]:
    """Build a parametric kindred preset for a creature type.

    Matches cards that are that type (via ``type_line``), reference that
    type in oracle text (payoffs like "Goblins you control get +1/+0"
    or "whenever an Elf enters"), OR have the Changeling keyword
    (Mistform Ultimus, Universal Automaton, Mirror Entity — Changeling
    cards count as every creature type per CR 702.73, so they belong in
    every kindred theme). Irregular plurals for common types (Elf/Elves,
    Wolf/Wolves, Dwarf/Dwarves, Werewolf/Werewolves) are handled by the
    plural map; other types get "s" appended.
    """
    t = creature_type.strip()
    if not t:
        raise click.BadParameter("--kindred value cannot be empty")

    key = t.lower()
    plural = _KINDRED_IRREGULAR_PLURALS.get(key, key + "s")
    oracle_alternatives = f"{re.escape(key)}|{re.escape(plural)}"
    oracle_pattern = re.compile(rf"\b(?:{oracle_alternatives})\b", re.IGNORECASE)
    type_pattern = re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)

    name = f"kindred-{key}"
    description = (
        f"Kindred ({t}): creatures of type {t} (including Changeling) "
        f"plus oracle-text payoffs that reference {t}/{plural}."
    )
    preset = Preset(
        name=name,
        description=description,
        keywords=("Changeling",),
        patterns=(oracle_pattern,),
        type_patterns=(type_pattern,),
    )
    return name, preset


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
    themes: dict[str, Preset],
    *,
    min_density: int | None = None,
    warn_density: int | None = None,
    include_commanders: bool = False,
    rewrites: tuple[tuple[str, str], ...] = (),
) -> dict:
    """Cross-reference themes against cards in the cube.

    ``themes`` maps theme names to :class:`Preset` objects. Callers who
    have a bare :class:`re.Pattern` should wrap it: ``Preset(name=..,
    description=.., patterns=(pattern,))``.

    ``include_commanders`` additionally iterates ``cube["commanders"]``
    (deck JSONs from parse-deck) and ``cube["commander_pool"]`` (cube
    JSONs from parse-cube). The two keys are disjoint in practice, so
    reading both covers commander decks and PDH cubes with one flag.

    ``rewrites`` is a tuple of ``(source_theme, dest_theme)`` pairs that
    widen ``dest_theme``'s matcher with an OR against ``source_theme``'s
    preset. Captures commander-induced archetype shifts — a user with a
    "whenever an elf enters, drain 1" commander can pass
    ``("kindred-elf", "drain")`` to have elves count toward drain without
    needing the drain regex to match them. Both names must exist as keys
    in ``themes``.

    ``min_density`` and ``warn_density`` both interpret ``0`` as
    "suppress the corresponding note" (threshold is literally zero, so
    no total can fall below it). Pass ``None`` (or omit) to fall back to
    the balance-target default.
    """
    lookup = build_card_lookup(hydrated)
    targets = get_balance_targets(cube)
    threshold = (
        min_density
        if min_density is not None
        else int(targets.get("min_archetype_signal_density", 3))
    )
    warn_threshold = (
        warn_density
        if warn_density is not None
        else int(targets.get("warn_archetype_signal_density", 5))
    )

    entries: list[dict] = []
    if include_commanders:
        entries.extend(cube.get("commanders", []) or [])
        entries.extend(cube.get("commander_pool", []) or [])
    entries.extend(cube.get("cards", []) or [])

    # Deduplicate on name, keeping the first occurrence. Protects against
    # hand-edited deck JSONs where the commander is present in both
    # ``commanders`` and ``cards`` — without this, including-commanders
    # would count the commander twice. If the duplicate entries carry
    # different quantities, the first one's quantity wins: behavior is
    # undefined for that case in practice (both copies almost always
    # carry quantity=1 for singleton formats).
    seen_names: set[str] = set()
    deduped_entries: list[dict] = []
    for entry in entries:
        name = entry.get("name")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        deduped_entries.append(entry)
    entries = deduped_entries

    # Validate rewrites and group by destination theme. Both source and
    # dest must be defined in ``themes`` — the user explicitly declares
    # both so the rewrite source is visible in its own theme bucket.
    rewrites_by_dest: dict[str, list[Preset]] = {}
    for source_name, dest_name in rewrites:
        if source_name not in themes:
            msg = (
                f"rewrite source {source_name!r} must be declared as a theme "
                "(via --preset, --kindred, --theme, or --from-cube)"
            )
            raise KeyError(msg)
        if dest_name not in themes:
            msg = (
                f"rewrite dest {dest_name!r} must be declared as a theme "
                "(via --preset, --kindred, --theme, or --from-cube)"
            )
            raise KeyError(msg)
        rewrites_by_dest.setdefault(dest_name, []).append(themes[source_name])

    # Build: per-theme list of matching cards (with color identity info).
    per_theme: dict[str, dict] = {}
    for theme_name, preset in themes.items():
        rewrite_sources = rewrites_by_dest.get(theme_name, [])
        matches: list[dict] = []
        for entry in entries:
            card = lookup.get(entry["name"])
            if card is None:
                continue
            if is_land(card):
                continue
            if not preset.matches(card) and not any(
                src.matches(card) for src in rewrite_sources
            ):
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


def render_text_report(audit: dict, *, show_matches: bool = False) -> str:
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
        if show_matches:
            cards = info.get("cards") or []
            if cards:
                lines.append("  matches: " + ", ".join(cards))
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


def _format_preset_catalog() -> str:
    """Render the preset registry as one-line name:description entries."""
    entries = list_presets()
    width = max((len(n) for n in entries), default=0)
    lines = [f"{len(entries)} preset(s) available:", ""]
    for name, desc in entries.items():
        lines.append(f"  {name.ljust(width)}  {desc}")
    return "\n".join(lines) + "\n"


@click.command()
@click.argument(
    "cube_path",
    type=click.Path(exists=True, path_type=Path),
    required=False,
)
@click.argument(
    "hydrated_path",
    type=click.Path(exists=True, path_type=Path),
    required=False,
)
@click.option(
    "--theme",
    "theme_specs",
    multiple=True,
    help="Theme definition 'name=regex'. Repeatable. Uses Python regex syntax.",
)
@click.option(
    "--preset",
    "preset_names",
    multiple=True,
    help=(
        "Load a named preset from the theme_presets registry (repeatable). "
        "See --list-presets for the catalog."
    ),
)
@click.option(
    "--kindred",
    "kindred_types",
    multiple=True,
    help=(
        "Build a parametric kindred/tribal theme for a creature type "
        "(e.g. --kindred Elf). Matches cards of that type via type_line "
        "AND oracle-text payoffs that reference the type/plural. "
        "Changeling cards match every kindred theme. Repeatable; "
        "irregular plurals like Elf/Elves, Wolf/Wolves, Dwarf/Dwarves "
        "are handled automatically. The generated theme is named "
        "kindred-<lowercase-type> (e.g. 'kindred-elf'), which is the "
        "name you reference in --rewrite rules."
    ),
)
@click.option(
    "--rewrite",
    "rewrite_specs",
    multiple=True,
    help=(
        "Rewrite rule 'source -> dest': cards matching the source theme "
        "also count toward dest. Captures commander-induced archetype "
        "shifts — e.g. --rewrite 'kindred-elf -> drain' for a commander "
        "that drains life whenever an elf enters. Both names must be "
        "declared as themes in the same invocation."
    ),
)
@click.option(
    "--list-presets",
    "list_presets_flag",
    is_flag=True,
    default=False,
    help="Print the preset catalog and exit (cube/hydrated args not required).",
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
    "--warn-density",
    type=int,
    default=None,
    help=(
        "Override warn threshold (themes below this count are flagged as "
        "thin-by-conventional-standards). Useful at deck scale where the "
        "cube-tuned default of 5 is miscalibrated."
    ),
)
@click.option(
    "--include-commanders",
    "include_commanders",
    is_flag=True,
    default=False,
    help=(
        "Also iterate entries under the cube/deck's 'commanders' key (parse-"
        "deck output) and 'commander_pool' key (parse-cube output) when "
        "counting theme matches. Pass this for Commander/Brawl/Historic "
        "Brawl decks — otherwise the commander is silently excluded. "
        "For PDH cubes, factors commander_pool entries into theme density."
    ),
)
@click.option(
    "--show-matches",
    "show_matches",
    is_flag=True,
    default=False,
    help=(
        "Include per-theme card-name lists in the text report (always present "
        "in the JSON sidecar). Helpful for spot-checking regex accuracy."
    ),
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
    cube_path: Path | None,
    hydrated_path: Path | None,
    theme_specs: tuple[str, ...],
    preset_names: tuple[str, ...],
    kindred_types: tuple[str, ...],
    rewrite_specs: tuple[str, ...],
    min_density: int | None,
    warn_density: int | None,
    output_path: Path | None,
    *,
    list_presets_flag: bool,
    from_cube: bool,
    include_commanders: bool,
    show_matches: bool,
    emit_json: bool,
):
    """Cross-reference theme queries against color pairs in a cube.

    Themes can come from four sources (combined): ``--preset <name>`` for
    registry-backed themes, ``--kindred <type>`` for parametric tribal
    themes built on the fly, ``--theme name=regex`` for custom regex, and
    ``--from-cube`` to load stated_archetypes from the cube JSON. Any
    theme name can be used on either side of a ``--rewrite`` rule.

    \b
    Known limitation: themes match each card in isolation (the card's own
    keywords and oracle text). Commander-induced archetype shifts —
    "whenever an X enters, do Y" / "creatures you control have Z" / cost-
    reduction and payoff commanders — are NOT reflected in the count. A
    vanilla elf is not creature-removal to this tool even if your commander
    blights opponents when elves enter. Use ``--rewrite source -> dest``
    to propagate such shifts (e.g. ``--kindred Elf --rewrite
    "kindred-elf -> drain"``), or capture them in the per-card analysis
    that follows the mechanical pass.
    """
    # --list-presets short-circuits: no cube/hydrated needed.
    if list_presets_flag:
        click.echo(_format_preset_catalog(), nl=False)
        return

    if cube_path is None or hydrated_path is None:
        raise click.UsageError(
            "CUBE_PATH and HYDRATED_PATH are required unless --list-presets is given."
        )

    cube_content = cube_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    cube = json.loads(cube_content)
    hydrated = json.loads(hydrated_content)

    themes: dict[str, Preset] = {}

    if from_cube:
        from mtg_utils._archetype_resolver import (
            merge_member_presets,
            resolve_stated_archetypes,
        )
        from mtg_utils.theme_presets import PRESETS

        try:
            resolved = resolve_stated_archetypes(cube)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        # Preset references — pull each from the library by name.
        for name in resolved.preset_names:
            if name in themes:
                continue
            themes[name] = PRESETS[name]

        # Groups — synthesize a merged Preset per group.
        for group in resolved.groups:
            themes[group.name] = merge_member_presets(group.name, group.members)

        # Custom regex entries.
        for custom_entry in resolved.custom:
            pattern = re.compile(custom_entry.regex, re.IGNORECASE)
            themes[custom_entry.name] = Preset(
                name=custom_entry.name,
                description=f"designer_intent regex: {custom_entry.regex}",
                patterns=(pattern,),
            )

    for raw in preset_names:
        name, preset = _resolve_preset_flag(raw)
        themes[name] = preset

    for raw in kindred_types:
        name, preset = _build_kindred_preset(raw)
        themes[name] = preset

    for spec in theme_specs:
        name, preset = _parse_theme_flag(spec)
        themes[name] = preset

    if not themes:
        raise click.UsageError(
            "No themes specified. Pass --preset <name> (repeatable), "
            "--kindred <type> (repeatable), --theme name=regex "
            "(repeatable), or --from-cube."
        )

    rewrites = tuple(_parse_rewrite_flag(raw) for raw in rewrite_specs)
    for source, dest in rewrites:
        if source not in themes:
            raise click.BadParameter(
                f"rewrite source {source!r} is not a declared theme "
                f"(known: {', '.join(sorted(themes.keys()))})",
                param_hint="--rewrite",
            )
        if dest not in themes:
            raise click.BadParameter(
                f"rewrite dest {dest!r} is not a declared theme "
                f"(known: {', '.join(sorted(themes.keys()))})",
                param_hint="--rewrite",
            )

    result = archetype_audit(
        cube,
        hydrated,
        themes,
        min_density=min_density,
        warn_density=warn_density,
        include_commanders=include_commanders,
        rewrites=rewrites,
    )

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
        click.echo(render_text_report(result, show_matches=show_matches), nl=False)
        click.echo(f"\nFull JSON: {output_path}")
