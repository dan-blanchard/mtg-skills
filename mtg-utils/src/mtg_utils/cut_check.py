"""Cut-check: mechanical pre-grill analysis of cards under consideration for cutting.

Every read is over phase's corrected concept trees (``_card_ir.trees.trees_for``) and
the shared reads — triggers (``reads.trigger_kinds``) and their fixed values
(``reads.fixed_amount``), keyword interactions, self-recursion (the
``self-recurring`` preset over the ``self_recurring`` signal key), commander
multiplication (``_analysis.multipliers``, the same read the tuner protects cuts
with) and the zone grant. A card phase has no trees for (a set newer than
``PHASE_TAG``) reports no triggers, no recursion and no multiplication: cut-check
never guesses from oracle text. The multiplied-value math is unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path

import click

from mtg_utils._analysis.multipliers import (
    Commander,
    grant_abilities,
    multiplier_reasons,
)
from mtg_utils._card_ir.crosswalk import AbilityUnit, ConceptTree
from mtg_utils._card_ir.crosswalk.describe import unit_text
from mtg_utils._card_ir.crosswalk.reads import (
    TRIGGER_KINDS,
    bypasses_legend_rule,
    fixed_amount,
    has_combat_damage_trigger,
    limits_blockers_to_one,
    trigger_kinds,
)
from mtg_utils._card_ir.trees import object_facts, trees_for
from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import build_card_lookup
from mtg_utils.deck_cli import acquire_for_cli, bulk_data_option
from mtg_utils.hydrated_deck import sidecar_path
from mtg_utils.rules_lookup import (
    find_citations_for_terms,
    load_rules,
    resolve_rules_path,
)
from mtg_utils.theme_presets import matches as matches_preset


def _trigger_units(
    trees: Iterable[ConceptTree],
) -> Iterator[tuple[ConceptTree, AbilityUnit]]:
    for tree in trees:
        for unit in tree.iter_units("trigger"):
            yield tree, unit


def _any_tree(card: Mapping, read: Callable[[ConceptTree], bool]) -> bool:
    return any(read(tree) for tree in trees_for(dict(card)))


class CommanderProfile(Commander):
    """The commander as cut-check reads it, once per run: the multipliers' view
    (:class:`~mtg_utils._analysis.multipliers.Commander` — its trees, facts,
    triggers, non-mana activated abilities and zone grant) plus the trigger types
    it has and whether it limits blockers or has a combat-damage trigger."""

    def __init__(self, record: Mapping) -> None:
        super().__init__(record)
        types: list[str] = []
        for _tree, unit in _trigger_units(self.trees):
            types.extend(t for t in trigger_kinds(unit) if t not in types)
        self.trigger_types: tuple[str, ...] = tuple(types)
        self.limits_blockers = any(limits_blockers_to_one(t) for t in self.trees)
        self.combat_damage_trigger = any(
            has_combat_damage_trigger(t) for t in self.trees
        )


def commander_profile(commander: Mapping) -> CommanderProfile:
    return CommanderProfile(commander)


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


def detect_triggers(
    card: dict, *, trigger_types: list[str], opponents: int
) -> list[dict]:
    """The card's triggered abilities: ``text`` (the ability in words), ``types``
    (every trigger type it fires on, ``reads.trigger_kinds``),
    ``matches_trigger_type`` and ``matched_type`` (the first of ``types`` asked
    for), and ``parseable`` / ``base_value`` — the first fixed number the ability
    yields (``reads.fixed_amount``), damage to each opponent counted once per
    opponent (Purphoros, God of the Forge: 2 → 6 against three); the text when
    there is none."""
    results: list[dict] = []
    for tree, unit in _trigger_units(trees_for(dict(card))):
        text = unit_text(unit, tree.name)
        types = trigger_kinds(unit)
        matched = next((t for t in types if t in trigger_types), None)
        amount = fixed_amount(unit)
        value = None
        if amount is not None:
            value = amount.value * (opponents if amount.per_opponent else 1)
        results.append(
            {
                "text": text,
                "types": list(types),
                "matches_trigger_type": matched is not None,
                "matched_type": matched,
                "parseable": value is not None,
                "base_value": str(value) if value is not None else text,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Keyword interaction detection
# ---------------------------------------------------------------------------


def detect_keyword_interactions(card: dict, cmd: CommanderProfile) -> list[dict]:
    """Emergent keyword combinations between the card and the commander."""
    kws = object_facts(dict(card)).keywords | cmd.facts.keywords
    interactions: list[dict] = []

    # Menace: "can't be blocked except by two or more creatures" (CR 702.111b);
    # beside "can't be blocked by more than one creature" no block is legal, the
    # restrictions being cumulative (CR 509.1b).
    if "menace" in kws and (
        cmd.limits_blockers or _any_tree(card, limits_blockers_to_one)
    ):
        interactions.append(
            {
                "keywords": ["menace", "can't be blocked by more than one creature"],
                "interaction": (
                    "Unblockable: menace requires 2+ blockers,"
                    " but card restricts to 1 blocker"
                ),
            }
        )

    # Double strike deals combat damage in both combat damage steps (CR 702.4b),
    # so a combat-damage trigger fires twice.
    if "doublestrike" in kws and (
        cmd.combat_damage_trigger or _any_tree(card, has_combat_damage_trigger)
    ):
        interactions.append(
            {
                "keywords": ["double strike", "combat damage trigger"],
                "interaction": (
                    "Double triggers: double strike causes"
                    " combat damage trigger to fire twice"
                ),
            }
        )

    # Any nonzero combat damage from a deathtouch source is lethal for assigning
    # trample damage (CR 702.2c, 702.19b).
    if "trample" in kws and "deathtouch" in kws:
        interactions.append(
            {
                "keywords": ["trample", "deathtouch"],
                "interaction": (
                    "Trample + deathtouch: 1 damage kills, rest tramples over"
                ),
            }
        )

    return interactions


# ---------------------------------------------------------------------------
# Self-recurring, commander multiplication, zone grant
# ---------------------------------------------------------------------------


def detect_self_recurring(card: dict) -> bool:
    """Whether the card brings itself back for another use — the
    ``self-recurring`` preset (``lanes.card_advantage.recurs_itself``)."""
    return matches_preset("self-recurring", card)


def detect_commander_multiplication(card: dict, cmd: CommanderProfile) -> dict:
    """Whether the card copies the commander or multiplies its abilities.

    Returns a dict with:
        - commander_copy: ``{"type", "clause"}`` per way it copies the commander
        - ability_copy: the same per way it copies or doubles its abilities
        - legend_bypass: whether the card gets around the legend rule
        - commander_triggers_affected: the commander's trigger types
        - commander_activated_abilities: the commander's non-mana activated
          abilities (both only when the card copies or multiplies)
    """
    reasons = multiplier_reasons(card, cmd)
    by_family: dict[str, list[dict]] = {"copy": [], "ability": []}
    for r in reasons:
        if r.family in by_family:
            by_family[r.family].append({"type": r.kind, "clause": r.clause})
    multiplies = bool(by_family["copy"] or by_family["ability"])
    return {
        "commander_copy": by_family["copy"],
        "ability_copy": by_family["ability"],
        "legend_bypass": _any_tree(card, bypasses_legend_rule),
        "commander_triggers_affected": list(cmd.trigger_types) if multiplies else [],
        "commander_activated_abilities": (
            list(cmd.activated_texts) if multiplies else []
        ),
    }


def detect_zone_granted_abilities(card: dict, cmd: CommanderProfile) -> dict:
    """Abilities the commander borrows from this card in a non-battlefield zone.

    For a commander like Thranduil, the Elvenking, a matching card's activated
    abilities are live *from the graveyard* — so cutting it strips a tool off
    the commander even though the card need never be cast. Nothing else in
    cut-check models this: ``detect_triggers`` reads triggered abilities and
    ``detect_commander_multiplication`` only fires when the cut card copies the
    commander, so a card whose whole value is "its activated ability, from the
    yard" otherwise produces zero signal (``multipliers.grant_abilities``).

    Returns ``{"grants": False}`` when the commander has no such ability.
    """
    grant = cmd.grant
    if grant is None:
        return {"grants": False}
    abilities = grant_abilities(card, grant)
    return {
        "grants": True,
        "granted_type": grant.card_type,
        "zone": grant.zone,
        "card_matches_type": abilities is not None,
        "abilities": abilities or [],
    }


# ---------------------------------------------------------------------------
# run_cut_check
# ---------------------------------------------------------------------------


def run_cut_check(
    *,
    hydrated: list[dict],
    commander_name: str,
    cut_names: list[str],
    trigger_types: list[str],
    multiplier_low: int,
    multiplier_high: int,
    opponents: int = 3,
) -> list[dict]:
    """Run full mechanical analysis for each card in cut_names."""
    lookup = build_card_lookup(hydrated)
    cmd = commander_profile(lookup.get(commander_name, {}))
    results: list[dict] = []

    for name in cut_names:
        card = lookup.get(name, {"name": name, "keywords": []})
        triggers = detect_triggers(
            card, trigger_types=trigger_types, opponents=opponents
        )

        # Add multiplied values for parseable matching triggers
        enriched_triggers: list[dict] = []
        for t in triggers:
            entry = dict(t)
            if t["matches_trigger_type"] and t["parseable"]:
                try:
                    val = float(t["base_value"])
                    entry["multiplied_low"] = f"{val * multiplier_low:.4g}"
                    entry["multiplied_high"] = f"{val * multiplier_high:.4g}"
                except ValueError:
                    pass
            enriched_triggers.append(entry)

        results.append(
            {
                "name": name,
                "triggers": enriched_triggers,
                "keyword_interactions": detect_keyword_interactions(card, cmd),
                "self_recurring": detect_self_recurring(card),
                "commander_multiplication": detect_commander_multiplication(card, cmd),
                "zone_granted_abilities": detect_zone_granted_abilities(card, cmd),
            }
        )

    return results


# ---------------------------------------------------------------------------
# Text report rendering
# ---------------------------------------------------------------------------


def _summarize_triggers(triggers: list[dict]) -> str:
    """Produce a one-line fragment describing a card's flagged triggers."""
    matching = [t for t in triggers if t.get("matches_trigger_type")]
    if not matching:
        return "triggers=0"
    parts: list[str] = []
    for t in matching:
        mtype = t.get("matched_type") or "?"
        low = t.get("multiplied_low")
        high = t.get("multiplied_high")
        if low is not None and high is not None:
            if low == high:
                parts.append(f"{mtype}={low}")
            else:
                parts.append(f"{mtype}={low}-{high}")
        else:
            parts.append(mtype)
    return f"triggers={len(matching)} ({', '.join(parts)})"


def _summarize_multiplication(mult: dict) -> str:
    """Return 'COMMANDER_MULTIPLICATION (reasons)' or empty string."""
    reasons: list[str] = []
    if mult.get("commander_copy"):
        reasons.append("commander_copy")
    if mult.get("ability_copy"):
        reasons.append("ability_copy")
    if mult.get("legend_bypass"):
        reasons.append("legend_bypass")
    if not reasons:
        return ""
    return f"COMMANDER_MULTIPLICATION ({', '.join(reasons)})"


def render_text_report(
    results: list[dict],
    *,
    commander_name: str,
    multiplier_low: int,
    multiplier_high: int,
    opponents: int,
) -> str:
    """Render run_cut_check results as a human-readable report."""
    lines: list[str] = []
    lines.append(
        f"cut-check: {len(results)} cards against {commander_name} "
        f"({multiplier_low}x-{multiplier_high}x multiplier, {opponents} opponents)"
    )
    lines.append("")

    flag_counts = {
        "commander_multiplication": 0,
        "trigger": 0,
        "self_recurring": 0,
        "keyword_interactions": 0,
        "zone_granted": 0,
    }

    for entry in results:
        name = entry["name"]
        bits: list[str] = []
        mult_str = _summarize_multiplication(entry["commander_multiplication"])
        if mult_str:
            bits.append(mult_str)
            flag_counts["commander_multiplication"] += 1
        trig_str = _summarize_triggers(entry["triggers"])
        bits.append(trig_str)
        if any(t.get("matches_trigger_type") for t in entry["triggers"]):
            flag_counts["trigger"] += 1
        if entry["self_recurring"]:
            bits.append("self-recurring=yes")
            flag_counts["self_recurring"] += 1
        else:
            bits.append("self-recurring=no")
        ki_count = len(entry["keyword_interactions"])
        bits.append(f"keyword-interactions={ki_count}")
        if ki_count:
            flag_counts["keyword_interactions"] += 1
        zone = entry.get("zone_granted_abilities") or {}
        zone_abilities = zone.get("abilities") or []
        if zone_abilities:
            bits.append(
                f"ZONE_GRANTED ({len(zone_abilities)} ability(s) the commander "
                f"loses from {zone['zone']})"
            )
            flag_counts["zone_granted"] += 1
        lines.append(f"  {name}: {', '.join(bits)}")

    lines.append("")
    lines.append(
        f"Flags: {flag_counts['commander_multiplication']} commander_multiplication, "
        f"{flag_counts['trigger']} trigger, "
        f"{flag_counts['self_recurring']} self-recurring, "
        f"{flag_counts['keyword_interactions']} keyword-interactions, "
        f"{flag_counts['zone_granted']} zone-granted"
    )
    # A commander that reads a zone makes every matching cut load-bearing, so
    # say so once rather than leaving the agent to infer it from the per-card
    # lines. Silence on a commander's defining mechanic reads as "no issues".
    zone_meta = next(
        (
            e["zone_granted_abilities"]
            for e in results
            if (e.get("zone_granted_abilities") or {}).get("grants")
        ),
        None,
    )
    if zone_meta:
        lines.append(
            f"NOTE: {commander_name} has all activated abilities of "
            f"{zone_meta['granted_type']} cards in your {zone_meta['zone']} — a "
            f"cut with a ZONE_GRANTED flag removes a tool from the commander "
            f"even though the card never has to be cast."
        )
    # Surface a CR-citations lookup failure at the bottom of the
    # summary. Per-entry ``rule_citations_error`` strings are all the
    # same (same resolve failure), so we emit the message once.
    errs = {
        e.get("rule_citations_error") for e in results if e.get("rule_citations_error")
    }
    for err in errs:
        lines.append(f"WARN: rule_citations not attached — {err}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_output_path(
    deck_path: Path,
    commander_name: str,
    cuts_content: str,
    multiplier_low: int,
    multiplier_high: int,
    opponents: int,
    trigger_types: tuple[str, ...],
) -> Path:
    """Hash every argument that affects the output, including --trigger-type.

    trigger_types IS consumed by run_cut_check (it filters which triggers
    count), so two invocations with different --trigger-type lists produce
    different results and must not share a cache file.
    """
    # Sort trigger_types so invocation order doesn't affect the hash.
    return sha_keyed_path(
        "cut-check",
        deck_path.read_text(encoding="utf-8"),
        sidecar_path(deck_path),
        commander_name,
        cuts_content,
        multiplier_low,
        multiplier_high,
        opponents,
        tuple(sorted(trigger_types)),
    )


def _attach_rule_citations(
    results: list[dict],
    rules_file: Path | None,
    input_path: Path | None = None,
) -> None:
    """Enrich each result with CR citations for its flagged keywords.

    For every entry in ``keyword_interactions``, look up the first term
    in the glossary and attach the ``see_rules`` rules as a new
    ``rule_citations`` field. Silently no-ops if the rules file can't be
    found — ``--cite-rules`` is additive, not a hard gate.

    ``input_path`` is passed through to ``resolve_rules_path`` so the
    default search can find a CR sitting next to the hydrated JSON
    (typical layout when the agent ran ``download-rules --output-dir
    <wd>`` in the same working dir as the rest of the tuning files).
    """
    try:
        path = resolve_rules_path(rules_file, input_path=input_path)
    except FileNotFoundError as exc:
        # Preserve the existing contract (run always succeeds) — surface
        # the miss as a note, not an error.
        for entry in results:
            entry["rule_citations"] = []
            entry["rule_citations_error"] = str(exc)
        return

    parsed = load_rules(path)
    for entry in results:
        terms: list[str] = []
        for ki in entry.get("keyword_interactions", []):
            for kw in ki.get("keywords", []):
                # Keep short, single-word-ish keywords; skip descriptive
                # fragments like "can't be blocked by more than one
                # creature" which aren't glossary terms.
                if len(kw.split()) <= 3:
                    terms.append(kw)
        entry["rule_citations"] = find_citations_for_terms(parsed, terms)


@click.command()
@click.argument("deck_path", type=click.Path(exists=True, path_type=Path))
@bulk_data_option
@click.option(
    "--commander",
    "commander_name",
    default=None,
    help="Which commander's abilities to check (default: the deck's first "
    "commander; pass the other partner to check them instead).",
)
@click.option(
    "--cuts",
    "cuts_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="JSON file containing a list of card name strings.",
)
@click.option(
    "--trigger-type",
    "trigger_types",
    multiple=True,
    type=click.Choice(TRIGGER_KINDS),
    help="Trigger type to check (may be repeated).",
)
@click.option(
    "--multiplier-low", required=True, type=int, help="Low-end trigger multiplier."
)
@click.option(
    "--multiplier-high", required=True, type=int, help="High-end trigger multiplier."
)
@click.option(
    "--opponents", default=3, show_default=True, type=int, help="Number of opponents."
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON output.",
)
@click.option(
    "--cite-rules/--no-cite-rules",
    "cite_rules",
    default=True,
    show_default=True,
    help=(
        "Attach MTG Comprehensive Rules citations for flagged keyword "
        "interactions. Pass --no-cite-rules to skip. When no CR file is "
        "found next to the deck JSON or in cwd, citations are "
        "silently omitted (with an error note in the JSON)."
    ),
)
@click.option(
    "--rules-file",
    "rules_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Comprehensive Rules TXT path. Defaults to newest comprehensive-rules*.txt.",
)
def main(
    deck_path: Path,
    bulk_data: Path | None,
    commander_name: str | None,
    cuts_path: Path,
    trigger_types: tuple[str, ...],
    multiplier_low: int,
    multiplier_high: int,
    opponents: int,
    output_path: Path | None,
    rules_file: Path | None,
    *,
    cite_rules: bool,
) -> None:
    """Run mechanical pre-grill analysis on candidate cuts from DECK_PATH."""
    hd = acquire_for_cli(deck_path, bulk_data)
    if commander_name is None:
        if not hd.commanders:
            raise click.ClickException(
                'the deck has no commander; pass --commander "<Name>" to name '
                "the card whose abilities the cuts interact with."
            )
        commander_name = hd.commanders[0]["name"]
    cuts_content = cuts_path.read_text(encoding="utf-8")
    raw_cuts = json.loads(cuts_content)
    # Accept both ``["Card Name", ...]`` and ``[{"name": ..., "quantity": ...}]``
    # so a single ``cuts.json`` can be shared with build-deck without rewriting.
    # Quantity is irrelevant for mechanical analysis (each card's text is the
    # same regardless of how many copies are cut), so we only need the names.
    # Reject malformed entries hard — symmetric with ``build_deck.normalize_entry``.
    # Asymmetric error policy (cut-check warns, build-deck raises) would let the
    # user trust a partial cut-check report, then surprise them with a hard error
    # from build-deck on the same input file.
    cut_names: list[str] = []
    for entry in raw_cuts:
        if isinstance(entry, str):
            cut_names.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            cut_names.append(entry["name"])
        else:
            raise click.ClickException(
                "cuts entry must be a card name string or "
                f'{{"name": ..., "quantity": ...}} dict, got: {entry!r}'
            )

    results = run_cut_check(
        hydrated=hd.records,
        commander_name=commander_name,
        cut_names=cut_names,
        trigger_types=list(trigger_types),
        multiplier_low=multiplier_low,
        multiplier_high=multiplier_high,
        opponents=opponents,
    )

    if cite_rules:
        _attach_rule_citations(results, rules_file, input_path=deck_path)

    if output_path is None:
        output_path = _default_output_path(
            deck_path,
            commander_name,
            cuts_content,
            multiplier_low,
            multiplier_high,
            opponents,
            trigger_types,
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, results)

    click.echo(
        render_text_report(
            results,
            commander_name=commander_name,
            multiplier_low=multiplier_low,
            multiplier_high=multiplier_high,
            opponents=opponents,
        ),
        nl=False,
    )
    click.echo(f"\nFull JSON: {output_path}")
