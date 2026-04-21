"""Cut-check: mechanical pre-grill analysis of cards under consideration for cutting."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path
from mtg_utils.card_classify import build_card_lookup, get_oracle_text
from mtg_utils.rules_lookup import (
    find_citations_for_terms,
    load_rules,
    resolve_rules_path,
)

# ---------------------------------------------------------------------------
# Trigger type patterns
# ---------------------------------------------------------------------------

_TRIGGER_PATTERNS: dict[str, list[str]] = {
    "upkeep": [
        r"At the beginning of your upkeep",
    ],
    "attack": [
        r"Whenever you attack",
        r"Whenever \S.*? attacks",
    ],
    "combat-damage": [
        r"Whenever \S.*? deals combat damage",
    ],
    "death": [
        r"Whenever \S.*? dies",
        r"Whenever a creature dies",
    ],
    "etb": [
        r"When \S.*? enters",
        r"Whenever \S.*? enters",
    ],
    "endstep": [
        r"At the beginning of (?:your|each) end step",
    ],
}

# Sentence splitter — split on newlines and periods followed by whitespace/cap
_SENTENCE_RE = re.compile(r"(?:\n|(?<=\.)\s+)")

# Trigger sentence openers
_TRIGGER_OPENER_RE = re.compile(
    r"^(At the beginning of|Whenever|When)\b", re.IGNORECASE
)

# Value parsers
_DAMAGE_N_RE = re.compile(r"deals?\s+(\d+)\s+damage", re.IGNORECASE)
_DAMAGE_EACH_OPPONENT_RE = re.compile(
    r"deals?\s+(\d+)\s+damage\s+to\s+each\s+opponent", re.IGNORECASE
)
_LIFE_N_RE = re.compile(r"gain\s+(\d+)\s+life", re.IGNORECASE)
_LIFE_EQUAL_RE = re.compile(r"gain\s+life\s+equal", re.IGNORECASE)
_TOKEN_N_RE = re.compile(r"create\s+(\d+)\s+\S.*?token", re.IGNORECASE)
_TOKEN_AN_RE = re.compile(r"create\s+(?:a|an)\s+\S.*?token", re.IGNORECASE)
_DRAW_N_RE = re.compile(r"draw\s+(\d+)\s+card", re.IGNORECASE)
_DRAW_A_RE = re.compile(r"draw\s+a\s+card", re.IGNORECASE)


def _parse_value(sentence: str, opponents: int) -> tuple[bool, str]:
    """Try to parse a fixed numeric value from a trigger sentence.

    Returns (parseable, base_value).
    """
    result = _try_parse_value(sentence, opponents)
    if result is not None:
        return True, result
    return False, sentence.strip()


def _try_parse_value(sentence: str, opponents: int) -> str | None:
    """Return parsed value string, or None if unparseable."""
    # Damage to each opponent — multiply
    m = _DAMAGE_EACH_OPPONENT_RE.search(sentence)
    if m:
        return str(int(m.group(1)) * opponents)

    # Plain damage N
    m = _DAMAGE_N_RE.search(sentence)
    if m:
        return m.group(1)

    # Life equal to damage (copy damage value from same sentence)
    if _LIFE_EQUAL_RE.search(sentence):
        md = _DAMAGE_EACH_OPPONENT_RE.search(sentence)
        if md:
            return str(int(md.group(1)) * opponents)
        md = _DAMAGE_N_RE.search(sentence)
        if md:
            return md.group(1)
        return "equal to damage"

    # Life N
    m = _LIFE_N_RE.search(sentence)
    if m:
        return m.group(1)

    # Token N
    m = _TOKEN_N_RE.search(sentence)
    if m:
        return m.group(1)

    # Token a/an → 1
    if _TOKEN_AN_RE.search(sentence):
        return "1"

    # Draw N
    m = _DRAW_N_RE.search(sentence)
    if m:
        return m.group(1)

    # Draw a card → 1
    if _DRAW_A_RE.search(sentence):
        return "1"

    return None


def _split_trigger_sentences(oracle_text: str) -> list[str]:
    """Split oracle text into trigger sentences."""
    sentences = _SENTENCE_RE.split(oracle_text)
    return [s.strip() for s in sentences if _TRIGGER_OPENER_RE.match(s.strip())]


def _match_trigger_type(
    sentence: str, trigger_types: list[str]
) -> tuple[bool, str | None]:
    """Return (matches, matched_type|None)."""
    for ttype in trigger_types:
        patterns = _TRIGGER_PATTERNS.get(ttype, [])
        for pattern in patterns:
            if re.search(pattern, sentence, re.IGNORECASE):
                return True, ttype
    return False, None


def detect_triggers(
    card: dict,
    *,
    trigger_types: list[str],
    opponents: int,
) -> list[dict]:
    """Scan oracle text for triggered abilities and classify them."""
    oracle = get_oracle_text(card)
    sentences = _split_trigger_sentences(oracle)
    results: list[dict] = []
    for sentence in sentences:
        matches, matched_type = _match_trigger_type(sentence, trigger_types)
        parseable, base_value = _parse_value(sentence, opponents)
        results.append(
            {
                "text": sentence,
                "matches_trigger_type": matches,
                "matched_type": matched_type,
                "parseable": parseable,
                "base_value": base_value,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Keyword interaction detection
# ---------------------------------------------------------------------------

_CANT_BE_BLOCKED_MORE_THAN_ONE_RE = re.compile(
    r"can't be blocked by more than one creature", re.IGNORECASE
)
_DEALS_COMBAT_DAMAGE_RE = re.compile(r"deals combat damage", re.IGNORECASE)


def _card_keywords_lower(card: dict) -> set[str]:
    """Return lowercased set of keywords from keywords list + oracle text."""
    kws: set[str] = set()
    for kw in card.get("keywords", []):
        kws.add(kw.lower())
    oracle = get_oracle_text(card)
    # Pick up inline keyword declarations (e.g. "Double strike\n")
    for line in oracle.splitlines():
        stripped = line.strip().rstrip(".")
        if stripped and len(stripped.split()) <= 3:
            kws.add(stripped.lower())
    return kws


def detect_keyword_interactions(card: dict, commander: dict) -> list[dict]:
    """Detect emergent keyword combinations between card and commander."""
    card_kws = _card_keywords_lower(card)
    cmd_kws = _card_keywords_lower(commander)
    card_oracle = get_oracle_text(card)
    cmd_oracle = get_oracle_text(commander)

    all_card_kws = card_kws
    all_cmd_kws = cmd_kws

    interactions: list[dict] = []

    # menace (commander) + "can't be blocked by more than one creature" (card oracle)
    has_menace = "menace" in all_cmd_kws or "menace" in all_card_kws
    has_block_restrict = (
        _CANT_BE_BLOCKED_MORE_THAN_ONE_RE.search(card_oracle) is not None
        or _CANT_BE_BLOCKED_MORE_THAN_ONE_RE.search(cmd_oracle) is not None
    )
    if has_menace and has_block_restrict:
        interactions.append(
            {
                "keywords": ["menace", "can't be blocked by more than one creature"],
                "interaction": (
                    "Unblockable: menace requires 2+ blockers,"
                    " but card restricts to 1 blocker"
                ),
            }
        )

    # double strike (card) + combat damage trigger (commander oracle)
    has_double_strike = (
        "double strike" in all_card_kws or "double strike" in all_cmd_kws
    )
    has_combat_damage_trigger = (
        _DEALS_COMBAT_DAMAGE_RE.search(cmd_oracle) is not None
        or _DEALS_COMBAT_DAMAGE_RE.search(card_oracle) is not None
    )
    if has_double_strike and has_combat_damage_trigger:
        interactions.append(
            {
                "keywords": ["double strike", "combat damage trigger"],
                "interaction": (
                    "Double triggers: double strike causes"
                    " combat damage trigger to fire twice"
                ),
            }
        )

    # trample + deathtouch
    has_trample = "trample" in all_card_kws or "trample" in all_cmd_kws
    has_deathtouch = "deathtouch" in all_card_kws or "deathtouch" in all_cmd_kws
    if has_trample and has_deathtouch:
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
# Commander multiplication patterns
# ---------------------------------------------------------------------------

# Commander copy patterns — cards that create a permanent copy
_COMMANDER_COPY_PATTERNS: dict[str, re.Pattern[str]] = {
    "create_token_copy": re.compile(
        r"create[s]?\s+(?:a|an|one|two|\d+)\s+(?:\S+\s+)*?tokens?\s+"
        r"(?:that(?:'s|\s+is)\s+(?:a\s+)?)?cop(?:y|ies)\s+of",
        re.IGNORECASE,
    ),
    "becomes_copy": re.compile(
        r"(?:enter[s]?\s+(?:the\s+battlefield\s+)?as\s+(?:a\s+)?copy\s+of"
        r"|becomes?\s+a\s+copy\s+of)",
        re.IGNORECASE,
    ),
    "create_copy": re.compile(
        r"create[s]?\s+(?:a|an|one|two|\d+)\s+cop(?:y|ies)\s+of",
        re.IGNORECASE,
    ),
    "copy_creature_spell": re.compile(
        r"copy\s+target\s+creature\s+spell.*?isn(?:'t| not)\s+legendary",
        re.IGNORECASE,
    ),
}

# Ability copy patterns — cards that copy or double abilities
_ABILITY_COPY_PATTERNS: dict[str, re.Pattern[str]] = {
    "copy_triggered_ability": re.compile(
        r"copy\s+target\s+triggered\s+ability",
        re.IGNORECASE,
    ),
    "copy_activated_or_triggered": re.compile(
        r"copy\s+target\s+activated\s+or\s+triggered\s+ability",
        re.IGNORECASE,
    ),
    "copy_activated_ability": re.compile(
        r"copy\s+that\s+ability",
        re.IGNORECASE,
    ),
    "trigger_doubler": re.compile(
        r"triggers?\s+an\s+additional\s+time",
        re.IGNORECASE,
    ),
}

# Legend-rule bypass patterns
_LEGEND_BYPASS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"isn(?:'t| not)\s+legendary", re.IGNORECASE),
    re.compile(r"legend\s+rule.*?doesn(?:'t| not)\s+apply", re.IGNORECASE),
]

# Activated ability pattern — {cost}: effect (excluding mana abilities)
_ACTIVATED_ABILITY_RE = re.compile(r"\{[^}]+\}.*?:")
_MANA_ABILITY_RE = re.compile(r"^\{[^}]*\}(?:,\s*\{[^}]*\})*:\s*Add\s", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Self-recurring detection
# ---------------------------------------------------------------------------

_RECURRING_KEYWORD_RE = re.compile(
    r"\b(suspend|buyback|retrace|escape|flashback|encore)\b", re.IGNORECASE
)
_EXILE_TIME_COUNTER_RE = re.compile(r"exile.*?with.*?time counter", re.IGNORECASE)
_RETURN_TO_HAND_RE = re.compile(r"return.*?to.*?hand", re.IGNORECASE)


def detect_self_recurring(card: dict) -> bool:
    """Return True if the card has self-recursion mechanics."""
    oracle = get_oracle_text(card)
    keywords = [kw.lower() for kw in card.get("keywords", [])]

    # Check keywords list
    for kw in keywords:
        if _RECURRING_KEYWORD_RE.search(kw):
            return True

    # Check oracle text
    if _RECURRING_KEYWORD_RE.search(oracle):
        return True
    if _EXILE_TIME_COUNTER_RE.search(oracle):
        return True
    return bool(_RETURN_TO_HAND_RE.search(oracle))


# ---------------------------------------------------------------------------
# Commander multiplication detection
# ---------------------------------------------------------------------------


def _extract_activated_abilities(oracle_text: str) -> list[str]:
    """Extract non-mana activated abilities from oracle text."""
    abilities: list[str] = []
    for line in oracle_text.splitlines():
        stripped = line.strip()
        if _ACTIVATED_ABILITY_RE.match(stripped) and not _MANA_ABILITY_RE.match(
            stripped
        ):
            abilities.append(stripped)
    return abilities


def detect_commander_multiplication(card: dict, commander: dict) -> dict:
    """Detect whether a card can copy the commander or its abilities.

    Returns a dict with:
        - commander_copy: list of matched copy effects
        - ability_copy: list of matched ability-copy/doubler effects
        - legend_bypass: whether the card bypasses the legend rule
        - commander_triggers_affected: commander trigger types that would be multiplied
        - commander_activated_abilities: non-mana activated abilities on the commander
    """
    card_oracle = get_oracle_text(card)
    cmd_oracle = get_oracle_text(commander)

    commander_copy: list[dict] = []
    ability_copy: list[dict] = []
    legend_bypass = False

    for label, pattern in _COMMANDER_COPY_PATTERNS.items():
        m = pattern.search(card_oracle)
        if m:
            commander_copy.append({"type": label, "matched_text": m.group(0)})

    for label, pattern in _ABILITY_COPY_PATTERNS.items():
        m = pattern.search(card_oracle)
        if m:
            ability_copy.append({"type": label, "matched_text": m.group(0)})

    for pattern in _LEGEND_BYPASS_PATTERNS:
        if pattern.search(card_oracle):
            legend_bypass = True
            break

    # Identify commander triggers that would be affected
    commander_triggers_affected: list[str] = []
    if commander_copy or ability_copy:
        cmd_sentences = _split_trigger_sentences(cmd_oracle)
        all_types = list(_TRIGGER_PATTERNS.keys())
        for sentence in cmd_sentences:
            _matches, matched_type = _match_trigger_type(sentence, all_types)
            if matched_type and matched_type not in commander_triggers_affected:
                commander_triggers_affected.append(matched_type)

    # Identify commander activated abilities
    commander_activated_abilities: list[str] = []
    if commander_copy or ability_copy:
        commander_activated_abilities = _extract_activated_abilities(cmd_oracle)

    return {
        "commander_copy": commander_copy,
        "ability_copy": ability_copy,
        "legend_bypass": legend_bypass,
        "commander_triggers_affected": commander_triggers_affected,
        "commander_activated_abilities": commander_activated_abilities,
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
    commander = lookup.get(commander_name, {})
    results: list[dict] = []

    for name in cut_names:
        card = lookup.get(name, {"name": name, "oracle_text": "", "keywords": []})
        triggers = detect_triggers(
            card, trigger_types=trigger_types, opponents=opponents
        )
        keyword_interactions = detect_keyword_interactions(card, commander)
        self_recurring = detect_self_recurring(card)
        commander_multiplication = detect_commander_multiplication(card, commander)

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
                "keyword_interactions": keyword_interactions,
                "self_recurring": self_recurring,
                "commander_multiplication": commander_multiplication,
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
        lines.append(f"  {name}: {', '.join(bits)}")

    lines.append("")
    lines.append(
        f"Flags: {flag_counts['commander_multiplication']} commander_multiplication, "
        f"{flag_counts['trigger']} trigger, "
        f"{flag_counts['self_recurring']} self-recurring, "
        f"{flag_counts['keyword_interactions']} keyword-interactions"
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_output_path(
    hydrated_content: str,
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
        hydrated_content,
        commander_name,
        cuts_content,
        multiplier_low,
        multiplier_high,
        opponents,
        tuple(sorted(trigger_types)),
    )


def _attach_rule_citations(results: list[dict], rules_file: Path | None) -> None:
    """Enrich each result with CR citations for its flagged keywords.

    For every entry in ``keyword_interactions``, look up the first term
    in the glossary and attach the ``see_rules`` rules as a new
    ``rule_citations`` field. Silently no-ops if the rules file can't be
    found — ``--cite-rules`` is additive, not a hard gate.
    """
    try:
        path = resolve_rules_path(rules_file)
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
                # Keep short, single-word-ish keywords; skip oracle-text
                # fragments like "can't be blocked by more than one
                # creature" which aren't glossary terms.
                if len(kw.split()) <= 3:
                    terms.append(kw)
        entry["rule_citations"] = find_citations_for_terms(parsed, terms)


@click.command()
@click.argument("hydrated_path", type=click.Path(exists=True, path_type=Path))
@click.argument("commander_name")
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
    "--cite-rules",
    "cite_rules",
    is_flag=True,
    help="Attach MTG Comprehensive Rules citations for flagged keyword interactions.",
)
@click.option(
    "--rules-file",
    "rules_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Comprehensive Rules TXT path. Defaults to newest comprehensive-rules*.txt.",
)
def main(
    hydrated_path: Path,
    commander_name: str,
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
    """Run mechanical pre-grill analysis on candidate cut cards."""
    hydrated_content = hydrated_path.read_text(encoding="utf-8")
    cuts_content = cuts_path.read_text(encoding="utf-8")
    hydrated = json.loads(hydrated_content)
    cut_names = json.loads(cuts_content)

    results = run_cut_check(
        hydrated=hydrated,
        commander_name=commander_name,
        cut_names=cut_names,
        trigger_types=list(trigger_types),
        multiplier_low=multiplier_low,
        multiplier_high=multiplier_high,
        opponents=opponents,
    )

    if cite_rules:
        _attach_rule_citations(results, rules_file)

    if output_path is None:
        output_path = _default_output_path(
            hydrated_content,
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
