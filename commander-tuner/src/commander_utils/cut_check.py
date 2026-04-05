"""Cut-check: mechanical pre-grill analysis of cards under consideration for cutting."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from commander_utils.card_classify import build_card_lookup

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
    oracle = card.get("oracle_text", "") or ""
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
    oracle = card.get("oracle_text", "") or ""
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
    card_oracle = card.get("oracle_text", "") or ""
    cmd_oracle = commander.get("oracle_text", "") or ""

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
    oracle = card.get("oracle_text", "") or ""
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
    card_oracle = card.get("oracle_text", "") or ""
    cmd_oracle = commander.get("oracle_text", "") or ""

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
# CLI
# ---------------------------------------------------------------------------


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
def main(
    hydrated_path: Path,
    commander_name: str,
    cuts_path: Path,
    trigger_types: tuple[str, ...],
    multiplier_low: int,
    multiplier_high: int,
    opponents: int,
) -> None:
    """Run mechanical pre-grill analysis on candidate cut cards."""
    hydrated = json.loads(hydrated_path.read_text(encoding="utf-8"))
    cut_names = json.loads(cuts_path.read_text(encoding="utf-8"))

    results = run_cut_check(
        hydrated=hydrated,
        commander_name=commander_name,
        cut_names=cut_names,
        trigger_types=list(trigger_types),
        multiplier_low=multiplier_low,
        multiplier_high=multiplier_high,
        opponents=opponents,
    )

    click.echo(json.dumps(results, indent=2))
