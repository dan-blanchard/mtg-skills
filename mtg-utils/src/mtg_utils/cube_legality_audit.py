"""Mechanical legality audit for an MTG cube.

Checks each card in a cube against the format's declared constraints:

  * ``rarity_filter`` — Pauper (commons only), Peasant (commons + uncommons),
    PDH main pool (commons only).
  * ``legality_key`` — Scryfall ``legalities[<key>]`` gate, e.g. Modern- or
    Legacy-legal cubes should not include banned cards.
  * ``ban_list`` — explicit per-format bans, e.g. the Power 9 for
    ``unpowered`` cubes.
  * ``commander_pool_rarity_filter`` — PDH commanders are traditionally
    uncommons only.

This is a hard-constraint check: violations are reported by severity
``error`` (format rules clearly violated) or ``warn`` (ambiguous — e.g.
the default-printing rarity may differ from a legal printing that exists
in another set). Unlike ``cube-balance``, which is purely informational,
this audit is intended to mechanically catch violations that a designer
or agent would otherwise miss.

Rarity caveat: Scryfall's ``rarity`` field is the *default* printing's
rarity; a card may be legal in Pauper if *any* printing is common, even
if the default printing isn't. For Pauper specifically, we prefer the
``legalities.pauper`` gate when available since it handles printing
nuances correctly. For Peasant (commons + uncommons), no Scryfall
legality exists, so we fall back to the default-printing rarity and
emit ``warn``-severity issues the designer should cross-check manually.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import build_card_lookup
from mtg_utils.cube_config import CUBE_FORMAT_CONFIGS, get_cube_config


def _check_rarity(
    card: dict,
    rarity_filter: frozenset[str] | None,
    *,
    use_scryfall_legality: bool = False,
    legality_key: str | None = None,
) -> tuple[str, str] | None:
    """Return ``(severity, reason)`` if the card violates rarity; else None."""
    if rarity_filter is None:
        return None

    # Prefer Scryfall legality when available (handles multi-printing logic).
    if use_scryfall_legality and legality_key:
        legalities = card.get("legalities") or {}
        status = legalities.get(legality_key)
        if status in ("legal", "restricted"):
            return None
        if status is None:
            return ("warn", f"no {legality_key} legality info in hydrated data")
        return ("error", f"not {legality_key}-legal (status: {status})")

    # Fall back to default-printing rarity. Emit 'warn' because a card with
    # a default-printing rare may have a common printing that would satisfy
    # the filter — the designer should cross-check.
    rarity = (card.get("rarity") or "").lower()
    if not rarity:
        return ("warn", "no rarity in hydrated data")
    if rarity not in rarity_filter:
        allowed = "/".join(sorted(rarity_filter))
        return (
            "warn",
            f"default printing is {rarity}; format allows {allowed} only — "
            f"verify no {allowed} printing exists in another set",
        )
    return None


def _check_legality_key(card: dict, legality_key: str | None) -> tuple[str, str] | None:
    if legality_key is None:
        return None
    legalities = card.get("legalities") or {}
    status = legalities.get(legality_key)
    if status in ("legal", "restricted"):
        return None
    if status is None:
        return ("warn", f"no {legality_key} legality info in hydrated data")
    return ("error", f"not {legality_key}-legal (status: {status})")


def cube_legality_audit(cube: dict, hydrated: list[dict]) -> dict:
    """Run all hard-constraint checks and return violations grouped by kind."""
    lookup = build_card_lookup(hydrated)
    cfg = get_cube_config(cube)

    rarity_filter = cfg.get("rarity_filter")
    commander_rarity_filter = cfg.get("commander_pool_rarity_filter")
    legality_key = cfg.get("legality_key")
    ban_list = set(cfg.get("ban_list") or [])

    # `rarity_filter == {common}` plus no other legality gate → Pauper-style
    # check. This predicate fires for both `pauper` and `pdh` formats; both
    # benefit from Scryfall's any-printing-common logic for the main pool.
    pauper_mode = rarity_filter == frozenset({"common"}) and legality_key is None
    rarity_legality_key = "pauper" if pauper_mode else None

    violations: list[dict] = []

    def record(card_name: str, section: str, severity: str, reason: str) -> None:
        violations.append(
            {
                "card": card_name,
                "section": section,
                "severity": severity,
                "reason": reason,
            }
        )

    for entry in cube.get("cards") or []:
        name = entry["name"]
        card = lookup.get(name)
        if card is None:
            record(name, "cards", "warn", "not found in hydrated data")
            continue

        if name in ban_list:
            record(
                name,
                "cards",
                "error",
                f"banned by format ({cube.get('cube_format')})",
            )

        rarity_issue = _check_rarity(
            card,
            rarity_filter,
            use_scryfall_legality=pauper_mode,
            legality_key=rarity_legality_key,
        )
        if rarity_issue:
            record(name, "cards", rarity_issue[0], rarity_issue[1])

        legality_issue = _check_legality_key(card, legality_key)
        if legality_issue:
            record(name, "cards", legality_issue[0], legality_issue[1])

    for entry in cube.get("commander_pool") or []:
        name = entry["name"]
        card = lookup.get(name)
        if card is None:
            record(name, "commander_pool", "warn", "not found in hydrated data")
            continue

        if name in ban_list:
            record(
                name,
                "commander_pool",
                "error",
                f"banned by format ({cube.get('cube_format')})",
            )

        # For PDH, the main-pool rarity_filter doesn't apply to commanders;
        # use commander_pool_rarity_filter instead.
        cmd_filter = commander_rarity_filter
        if cmd_filter is not None:
            issue = _check_rarity(card, cmd_filter)
            if issue:
                record(name, "commander_pool", issue[0], issue[1])

        legality_issue = _check_legality_key(card, legality_key)
        if legality_issue:
            record(name, "commander_pool", legality_issue[0], legality_issue[1])

    errors = [v for v in violations if v["severity"] == "error"]
    warnings = [v for v in violations if v["severity"] == "warn"]

    return {
        "cube_format": cube.get("cube_format"),
        "rarity_filter": sorted(rarity_filter) if rarity_filter else None,
        "commander_pool_rarity_filter": (
            sorted(commander_rarity_filter) if commander_rarity_filter else None
        ),
        "legality_key": legality_key,
        "ban_list_size": len(ban_list),
        "error_count": len(errors),
        "warn_count": len(warnings),
        "violations": violations,
    }


def render_text_report(result: dict) -> str:
    lines: list[str] = []
    lines.append(
        f"cube-legality-audit: {result['error_count']} error(s), "
        f"{result['warn_count']} warning(s) "
        f"(format: {result.get('cube_format')})"
    )
    if result.get("rarity_filter"):
        lines.append(f"  rarity filter: {', '.join(result['rarity_filter'])}")
    if result.get("commander_pool_rarity_filter"):
        lines.append(
            "  commander pool rarity filter: "
            + ", ".join(result["commander_pool_rarity_filter"])
        )
    if result.get("legality_key"):
        lines.append(f"  legality key: {result['legality_key']}")

    errors = [v for v in result["violations"] if v["severity"] == "error"]
    warnings = [v for v in result["violations"] if v["severity"] == "warn"]

    if errors:
        lines.append("")
        lines.append(f"Errors ({len(errors)}):")
        for v in errors[:50]:
            section = f" [{v['section']}]" if v["section"] != "cards" else ""
            lines.append(f"  ✗ {v['card']}{section}: {v['reason']}")
        if len(errors) > 50:
            lines.append(f"  ... and {len(errors) - 50} more")

    if warnings:
        lines.append("")
        lines.append(f"Warnings ({len(warnings)}):")
        for v in warnings[:50]:
            section = f" [{v['section']}]" if v["section"] != "cards" else ""
            lines.append(f"  · {v['card']}{section}: {v['reason']}")
        if len(warnings) > 50:
            lines.append(f"  ... and {len(warnings) - 50} more")

    if not errors and not warnings:
        lines.append("")
        lines.append("No violations detected.")

    return "\n".join(lines) + "\n"


@click.command()
@click.argument("cube_path", type=click.Path(exists=True, path_type=Path))
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
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
)
def main(
    cube_path: Path,
    hydrated_path: Path,
    output_path: Path | None,
    *,
    emit_json: bool,
):
    """Validate a cube against its format's rarity, legality, and ban rules."""
    cube_content = cube_path.read_text(encoding="utf-8")
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    cube = json.loads(cube_content)
    hydrated = json.loads(hydrated_content)

    if cube.get("cube_format") and cube["cube_format"] not in CUBE_FORMAT_CONFIGS:
        raise click.UsageError(
            f"Unknown cube_format {cube['cube_format']!r} in cube JSON"
        )

    result = cube_legality_audit(cube, hydrated)

    if output_path is None:
        output_path = sha_keyed_path(
            "cube-legality-audit", cube_content, hydrated_content
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
