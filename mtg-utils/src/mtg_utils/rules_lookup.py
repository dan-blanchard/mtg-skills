"""Comprehensive Rules parser and lookup CLI.

Parses the Wizards of the Coast Magic: The Gathering Comprehensive Rules
TXT file into a structured dict — sections, rules (categories /
top-level rules / subrules) and the glossary — and exposes a ``rules-lookup``
CLI for agent-driven queries.

Three query modes:

* ``--rule 702.19a`` — exact rule-number lookup. Returns the rule text,
  any worked examples, the parent category, and any cross-referenced
  rules extracted from the text.
* ``--term trample`` — glossary lookup. Returns the term's definition
  plus the rules it points at (``see_rules``).
* ``--grep "combat damage"`` — regex search across rule text. Returns up
  to ``--limit`` matching rule numbers with a short snippet each.

The CR text is parsed once and cached as a pickled sidecar next to the
source file (same convention as ``bulk_loader``). Invalidation is via
mtime comparison plus an on-disk version tag; concurrent writers are
safe because writes are atomic-rename.
"""

from __future__ import annotations

import contextlib
import json
import pickle
import re
from pathlib import Path
from typing import Any

import click

from mtg_utils._sidecar import atomic_write_json, sha_keyed_path

# On-disk pickle schema version; bump if the parsed shape changes.
_PARSED_VERSION = 1
_PARSED_SUFFIX = ".parsed.pkl"

# Section header: "1. Game Concepts" (single digit, title-cased words).
_SECTION_HEADER_RE = re.compile(r"^([1-9])\. (.+)$")

# Rule category header: "100. General" (three-digit number, no sub).
_RULE_CATEGORY_RE = re.compile(r"^(\d{3})\. (.+)$")

# Top-level rule: "100.1. These Magic rules apply...". The CR is mostly
# consistent but occasionally drops the period ("606.5 If...") or the
# trailing space ("901.4.All..."); accept both. Only the rule number
# itself is captured; the trailing period / space is optional.
_TOP_LEVEL_RULE_RE = re.compile(r"^(\d{3}\.\d+)\.?\s*(.+)$")

# Subrule: "100.1a A two-player game..." (lowercase letter; the CR
# usually omits the period after the letter but sometimes keeps it, as
# in "119.1d. In a two-player Brawl game"). Letters 'l' and 'o' are
# skipped in the CR to avoid 1/0 confusion, but we accept any lowercase
# letter for robustness.
_SUBRULE_RE = re.compile(r"^(\d{3}\.\d+[a-z])\.?\s*(.+)$")

# Worked example lines, always "Example: ..." at column 0.
_EXAMPLE_RE = re.compile(r"^Example:\s*(.+)$")

# Rule number reference inside prose — used to extract cross-references
# from both rule text and glossary definitions. Matches 3-digit category
# numbers ("113"), top-level rules ("100.1"), and subrules ("100.1a").
_RULE_REF_RE = re.compile(r"\b(\d{3}(?:\.\d+[a-z]?)?)\b")

# "These rules are effective as of February 2, 2024" — pulled from the
# preamble so the agent can cite the exact CR version.
_EFFECTIVE_DATE_RE = re.compile(
    r"effective as of ([A-Z][a-z]+ \d+, \d{4})",
)


def parse_rules(text: str) -> dict[str, Any]:
    """Parse the Comprehensive Rules TXT contents into a structured dict.

    The layout of the official TXT:

    1. Preamble (title, effective-date line, introduction paragraph).
    2. Table of contents — every section / category header is listed
       once, followed by the literals ``Glossary`` and ``Credits``.
    3. Body — the same section / category headers reappear, each
       followed by its rules, top-level rules, and subrules.
    4. Glossary — blank-line-separated term/definition blocks.
    5. Credits — copyright block we discard.

    We use the **second** occurrence of ``1. Game Concepts`` as the
    body-start marker (the first is the TOC entry), the first
    ``Glossary`` after that as the glossary start, and the first
    ``Credits`` after that as the end of the useful content.
    """
    lines = text.splitlines()

    effective_date = ""
    for line in lines[:15]:
        m = _EFFECTIVE_DATE_RE.search(line)
        if m:
            effective_date = m.group(1)
            break

    body_start = _find_body_start(lines)
    glossary_start = _find_line_after(lines, "Glossary", body_start)
    credits_start = _find_line_after(lines, "Credits", glossary_start + 1)
    if credits_start is None:
        credits_start = len(lines)

    sections, rules = _parse_body(lines[body_start:glossary_start])
    glossary = _parse_glossary(lines[glossary_start + 1 : credits_start])

    # Post-pass: drop any glossary ``see_rules`` reference that doesn't
    # resolve to a real rule number. Same filter ``_parse_body`` applied
    # to rule text so the two lists are consistent.
    for entry in glossary.values():
        entry["see_rules"] = sorted(
            {r for r in entry.get("see_rules", []) if _ref_exists(r, rules)},
        )

    return {
        "effective_date": effective_date,
        "sections": sections,
        "rules": rules,
        "glossary": glossary,
    }


def _find_body_start(lines: list[str]) -> int:
    """Return the line index of the body's ``1. Game Concepts`` header.

    The TOC lists it too, so we take the second match. Errors out if the
    second match is missing; a malformed CR is not something we silently
    half-parse.
    """
    seen = False
    for i, line in enumerate(lines):
        if line.strip() == "1. Game Concepts":
            if seen:
                return i
            seen = True
    msg = "Could not find body start (expected second '1. Game Concepts' line)"
    raise ValueError(msg)


def _find_line_after(lines: list[str], needle: str, start: int) -> int | None:
    for i in range(start, len(lines)):
        if lines[i].strip() == needle:
            return i
    return None


def _parse_body(lines: list[str]) -> tuple[dict[str, dict], dict[str, dict]]:
    """Parse the numbered-rules body into (sections, rules) dicts."""
    sections: dict[str, dict] = {}
    rules: dict[str, dict] = {}
    current_section: str | None = None
    current_rule: str | None = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue

        if m := _SECTION_HEADER_RE.match(stripped):
            current_section = m.group(1)
            sections[current_section] = {
                "title": m.group(2),
                "categories": [],
            }
            current_rule = None
            continue

        if m := _RULE_CATEGORY_RE.match(stripped):
            num = m.group(1)
            rules[num] = {
                "number": num,
                "kind": "category",
                "title": m.group(2),
                "text": "",
                "section": current_section,
                "examples": [],
            }
            if current_section:
                sections[current_section]["categories"].append(num)
            current_rule = num
            continue

        # Match SUBRULE before TOP_LEVEL_RULE: the relaxed TOP_LEVEL_RULE
        # regex (optional period, optional space) would otherwise swallow
        # a subrule like "119.1d In a game..." by capturing "119.1" and
        # "d In a game..." as the text.
        if m := _SUBRULE_RE.match(stripped):
            num = m.group(1)
            rules[num] = {
                "number": num,
                "kind": "subrule",
                "text": m.group(2),
                "section": current_section,
                "category": num.split(".")[0],
                "parent": num[:-1],
                "examples": [],
            }
            current_rule = num
            continue

        if m := _TOP_LEVEL_RULE_RE.match(stripped):
            num = m.group(1)
            rules[num] = {
                "number": num,
                "kind": "rule",
                "text": m.group(2),
                "section": current_section,
                "category": num.split(".")[0],
                "examples": [],
            }
            current_rule = num
            continue

        if m := _EXAMPLE_RE.match(stripped):
            if current_rule:
                rules[current_rule]["examples"].append(m.group(1))
            continue

        # Unmatched continuation line — append to the current rule's
        # prose. Rare in practice (the CR is well-formed), but harmless.
        if current_rule and rules[current_rule]["kind"] != "category":
            rules[current_rule]["text"] += " " + stripped

    # Extract cross-references once all text is assembled. Filter the
    # raw regex matches against the known rules/categories so that bare
    # numbers in prose ("deal 100 damage", "gain 20 life") don't appear
    # as spurious see_rules entries.
    for entry in rules.values():
        text = entry.get("text") or ""
        own_number = entry.get("number")
        refs = sorted(
            {
                ref
                for ref in _RULE_REF_RE.findall(text)
                if ref != own_number and _ref_exists(ref, rules)
            },
        )
        entry["see_rules"] = refs

    return sections, rules


def _ref_exists(ref: str, rules: dict[str, dict]) -> bool:
    """True when ``ref`` names a real rule, category, or subrule."""
    if ref in rules:
        return True
    # A top-level rule number (e.g. "113.3") implies the category
    # (e.g. "113") is indexed. But the regex also matches bare
    # categories like "113" directly, which may not appear as a top
    # key if the CR section header parse missed them — fall back to
    # prefix match.
    return any(r == ref or r.startswith(ref + ".") for r in rules)


def _parse_glossary(lines: list[str]) -> dict[str, dict]:
    """Parse the glossary: blank-line-separated Term / Definition blocks."""
    glossary: dict[str, dict] = {}
    current_term: str | None = None
    current_def: list[str] = []

    def flush() -> None:
        nonlocal current_term, current_def
        if current_term:
            definition = "\n".join(current_def).strip()
            # Raw refs — callers (``_parse_body``'s caller) filter these
            # against the actual rules dict. Glossary entries typically
            # cite the exact rule number so false positives are rarer
            # here than in rule text, but keeping the filter consistent
            # is easier than maintaining two different extraction paths.
            refs = sorted(set(_RULE_REF_RE.findall(definition)))
            glossary[current_term.lower()] = {
                "term": current_term,
                "definition": definition,
                "see_rules": refs,
            }
        current_term = None
        current_def = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            flush()
            continue
        if current_term is None:
            current_term = stripped
        else:
            current_def.append(stripped)

    flush()
    return glossary


# ---------------------------------------------------------------------------
# Parsed-cache sidecar
# ---------------------------------------------------------------------------


def _parsed_sidecar(rules_path: Path) -> Path:
    return rules_path.with_name(rules_path.name + _PARSED_SUFFIX)


def load_rules(rules_path: Path) -> dict[str, Any]:
    """Load + parse the CR, preferring a pickled sidecar cache.

    Mirrors ``bulk_loader.load_bulk_cards``: the sidecar is invalidated
    by mtime comparison, a version tag, or unpickle failure. Writes are
    atomic-rename so concurrent callers never observe a half-written
    cache.
    """
    sidecar = _parsed_sidecar(rules_path)
    if sidecar.exists() and sidecar.stat().st_mtime >= rules_path.stat().st_mtime:
        try:
            with sidecar.open("rb") as f:
                payload = pickle.load(f)
            if (
                isinstance(payload, dict)
                and payload.get("version") == _PARSED_VERSION
                and isinstance(payload.get("parsed"), dict)
            ):
                return payload["parsed"]
        except (pickle.PickleError, EOFError, OSError):
            pass  # fall through to reparse

    text = rules_path.read_text(encoding="utf-8")
    parsed = parse_rules(text)

    tmp = sidecar.with_name(sidecar.name + ".tmp")
    try:
        with tmp.open("wb") as f:
            pickle.dump(
                {"version": _PARSED_VERSION, "parsed": parsed},
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        tmp.replace(sidecar)
    except OSError:
        # Best-effort sidecar: clean up any partial .tmp so it doesn't
        # linger between runs. Next call just reparses.
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)

    return parsed


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def lookup_rule(parsed: dict[str, Any], number: str) -> dict | None:
    """Return a rule entry by canonical rule number, or None."""
    return parsed["rules"].get(number)


def lookup_term(parsed: dict[str, Any], term: str) -> dict | None:
    """Return a glossary entry by case-insensitive term match, or None."""
    return parsed["glossary"].get(term.lower())


def grep_rules(
    parsed: dict[str, Any],
    pattern: str,
    *,
    limit: int = 10,
    flags: int = re.IGNORECASE,
) -> list[dict]:
    """Regex-search rule text. Returns up to ``limit`` matches.

    Each match is ``{"number": ..., "kind": ..., "snippet": ...}`` where
    ``snippet`` is the matching line with ~60 chars of surrounding
    context. Category titles are searched too, so ``--grep "Turn
    Structure"`` hits the section-5 category list.
    """
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        msg = f"Invalid regex: {exc}"
        raise ValueError(msg) from exc

    results: list[dict] = []
    for num, entry in parsed["rules"].items():
        haystack = entry.get("text") or entry.get("title") or ""
        m = regex.search(haystack)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(haystack), m.end() + 40)
            snippet = haystack[start:end]
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(haystack) else ""
            results.append(
                {
                    "number": num,
                    "kind": entry["kind"],
                    "snippet": f"{prefix}{snippet}{suffix}",
                },
            )
            if len(results) >= limit:
                break
    return results


def find_citations_for_terms(
    parsed: dict[str, Any],
    terms: list[str],
) -> list[dict]:
    """Look up glossary terms and return ``{term, rule_number, snippet}``.

    Used by ``--cite-rules`` in other pipeline scripts to attach rule
    citations when a specific keyword (e.g., "double strike") is
    flagged. Misses are silently dropped; this is an enrichment, not a
    hard gate.
    """
    citations: list[dict] = []
    for term in terms:
        entry = parsed["glossary"].get(term.lower())
        if entry is None:
            continue
        for rule_num in entry["see_rules"]:
            rule = parsed["rules"].get(rule_num)
            if rule is None:
                continue
            citations.append(
                {
                    "term": entry["term"],
                    "rule": rule_num,
                    "snippet": (rule.get("text") or rule.get("title") or "")[:200],
                },
            )
    return citations


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------


def _render_rule(entry: dict) -> str:
    header = f"{entry['number']}. "
    if entry["kind"] == "category":
        header += entry["title"]
    else:
        header += entry["text"]
    lines = [header]
    for ex in entry.get("examples", []):
        lines.append(f"  Example: {ex}")
    if entry.get("see_rules"):
        lines.append(f"  See also: {', '.join(entry['see_rules'])}")
    return "\n".join(lines)


def _render_term(entry: dict) -> str:
    lines = [entry["term"], entry["definition"]]
    if entry["see_rules"]:
        lines.append(f"See rules: {', '.join(entry['see_rules'])}")
    return "\n".join(lines)


def _render_grep(matches: list[dict], pattern: str) -> str:
    if not matches:
        return f"rules-lookup: no matches for {pattern!r}"
    out = [f"rules-lookup: {len(matches)} match(es) for {pattern!r}"]
    for m in matches:
        out.append(f"  {m['number']} [{m['kind']}] {m['snippet']}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Default rules-file resolution
# ---------------------------------------------------------------------------


# Match the most recent release's filename regardless of year/date, so
# ``rules-lookup`` picks up the latest download without flags.
_DEFAULT_RULES_GLOB = "comprehensive-rules*.txt"


def _find_default_rules(search_dir: Path) -> Path | None:
    candidates = sorted(search_dir.glob(_DEFAULT_RULES_GLOB))
    return candidates[-1] if candidates else None


def resolve_rules_path(
    explicit: Path | None,
    cwd: Path | None = None,
    input_path: Path | None = None,
) -> Path:
    """Resolve the CR file path from an explicit flag or a glob search.

    Search order when ``explicit`` is None:

    1. The directory containing ``input_path`` (e.g. the deck JSON
       passed to legality-audit, the hydrated JSON passed to cut-check).
       This is where the user's working files live; if they ran
       ``download-rules --output-dir <wd>``, the CR is here too.
       Necessary because ``uv run --directory <skill>`` rebases
       ``Path.cwd()`` to the skill install dir, not the user's working
       dir, so a cwd-only search reliably misses the CR for agents
       invoking the CLI via that pattern.
    2. ``cwd`` (parameter) if set, else ``Path.cwd()``.

    Raises ``FileNotFoundError`` with an actionable message when no
    candidate exists. Matches the ``download-bulk`` pattern.
    """
    if explicit is not None:
        if not explicit.exists():
            msg = f"Rules file not found: {explicit}"
            raise FileNotFoundError(msg)
        return explicit

    searched: list[Path] = []
    if input_path is not None:
        candidate_dir = input_path.parent if input_path.is_file() else input_path
        searched.append(candidate_dir)
        found = _find_default_rules(candidate_dir)
        if found is not None:
            return found

    cwd_dir = cwd or Path.cwd()
    if cwd_dir not in searched:
        searched.append(cwd_dir)
        found = _find_default_rules(cwd_dir)
        if found is not None:
            return found

    locations = ", ".join(str(p) for p in searched)
    msg = (
        f"No comprehensive-rules*.txt found (searched: {locations}). "
        "Run `download-rules` first or pass --rules-file."
    )
    raise FileNotFoundError(msg)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--rule",
    "rule_number",
    default=None,
    help="Look up a rule by number (e.g., '702.19a').",
)
@click.option("--term", "glossary_term", default=None, help="Look up a glossary term.")
@click.option("--grep", "grep_pattern", default=None, help="Regex search rule text.")
@click.option(
    "--limit",
    default=10,
    show_default=True,
    type=int,
    help="Max --grep results.",
)
@click.option(
    "--rules-file",
    "rules_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to a comprehensive-rules*.txt file. Defaults to newest match in cwd.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Override the default sha-keyed path for the full JSON sidecar.",
)
@click.option("--json", "json_output", is_flag=True, help="Emit full JSON to stdout.")
def main(
    rule_number: str | None,
    glossary_term: str | None,
    grep_pattern: str | None,
    limit: int,
    rules_file: Path | None,
    output_path: Path | None,
    *,
    json_output: bool,
) -> None:
    """Look up MTG Comprehensive Rules entries by number, term, or regex."""
    mode_count = sum(1 for x in (rule_number, glossary_term, grep_pattern) if x)
    if mode_count != 1:
        msg = "Specify exactly one of --rule, --term, or --grep"
        raise click.UsageError(msg)

    path = resolve_rules_path(rules_file)
    parsed = load_rules(path)

    result: dict[str, Any]
    if rule_number:
        entry = lookup_rule(parsed, rule_number)
        if entry is None:
            click.echo(f"rules-lookup: no rule {rule_number!r} found")
            result = {"query": {"rule": rule_number}, "match": None}
        else:
            click.echo(_render_rule(entry))
            result = {"query": {"rule": rule_number}, "match": entry}
    elif glossary_term:
        entry = lookup_term(parsed, glossary_term)
        if entry is None:
            click.echo(f"rules-lookup: no glossary term {glossary_term!r}")
            result = {"query": {"term": glossary_term}, "match": None}
        else:
            click.echo(_render_term(entry))
            result = {"query": {"term": glossary_term}, "match": entry}
    else:
        # grep_pattern is guaranteed non-None by the mode_count check.
        pattern = grep_pattern or ""
        matches = grep_rules(parsed, pattern, limit=limit)
        click.echo(_render_grep(matches, pattern))
        result = {"query": {"grep": pattern, "limit": limit}, "matches": matches}

    result["effective_date"] = parsed["effective_date"]

    if output_path is None:
        output_path = sha_keyed_path(
            "rules-lookup",
            path,
            rule_number or "",
            glossary_term or "",
            grep_pattern or "",
            limit,
        )
    else:
        output_path = output_path.resolve()
    atomic_write_json(output_path, result)

    if json_output:
        click.echo(json.dumps(result, indent=2))
    click.echo(f"\nFull JSON: {output_path}")
