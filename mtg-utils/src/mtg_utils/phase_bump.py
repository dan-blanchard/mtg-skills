"""``bump-phase-pin <tag>`` — the scripted phase-rs pin bump (ADR-0028's validated
spike, ADR-0049).

A pin bump used to be a ~47-file change with three steps that lived only in a memory
note (the crosswalk fixture had no writer, the impostor census and the corpus signal
diff were re-derived by hand). This CLI runs the whole recipe in order and stops at
the first failure; ``--from-step N`` resumes. The script edits the pin and the
generated rosters, regenerates every artifact that has a builder, and writes ONE
markdown report that pre-sorts the triage: the impostor census (each row classified,
plus dead ``_IMPOSTOR_RECORDS`` rows), the per-key signal diff (every loss bucketed,
gains on already-parsed cards tagged), the losses still needing a verdict, the
RETIRE-READY rows, and every bridge row's corpus reach. How a person works the report
is ``docs/phase-pin-bump.md``.

Steps:
  1 pin                 PHASE_TAG, CLAUDE.md's "currently" mentions, the pin test
                        (live sites only — dated history mentions are kept)
  2 variants            EFFECT_VARIANTS from phase's ``ability.rs`` at the tag
  3 card-data           fetch + cache card-data.json for the tag
  4 substrate           build-card-ir-substrate; ZERO_INSTANCE_EFFECTS from the zeros
  5 impostor-census     card-data records whose text matches no bulk face, each
                        classified; dead ``_IMPOSTOR_RECORDS`` rows
  6 rebuild             copy the signals .pkl aside; snapshot, sidecar, signals index
  7 signal-diff         old vs new signals index, per key; losses bucketed, gains
                        tagged (reads the old tag's cached card-data + the tests)
  8 graduation          RETIRE-READY rows: test_bridge_ledger.py + every
                        ``retirement_canary``-marked test; bridge corpus reach

(The crosswalk suites' own fixture — step 5 until ADR-0056 merged it into the card
snapshot — is re-resolved by step 6's ``build-card-snapshot`` with everything else;
the builder's summary, unresolved names included, lands in the report's notes.)

Downstream builders run as subprocesses of the SAME interpreter, so they import the
freshly edited pin; this process only sets ``_phase.PHASE_TAG`` for its own fetches.
Gated: needs the local MTGJSON bulk, network for phase's release + raw source, and is
never run in CI (the pure pieces are unit-tested; the orchestration is dry-run over
fakes).
"""

from __future__ import annotations

import json
import pickle
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import click

from mtg_utils import _phase
from mtg_utils.deck_cli import bulk_data_option

if TYPE_CHECKING:
    from mtg_utils._analysis.bridge_ledger import Bridge
    from mtg_utils._card_ir.trees import ConceptTree

PHASE_RAW = "https://raw.githubusercontent.com/phase-rs/phase"
ABILITY_RS = "crates/engine/src/types/ability.rs"

VARIANTS_BEGIN = "# BEGIN GENERATED EFFECT_VARIANTS"
VARIANTS_END = "# END GENERATED EFFECT_VARIANTS"
ZERO_BEGIN = "# BEGIN GENERATED ZERO_INSTANCE_EFFECTS"
ZERO_END = "# END GENERATED ZERO_INSTANCE_EFFECTS"

# Repo-relative paths the bump edits or reads.
PIN_FILE = Path("mtg-utils/src/mtg_utils/_phase.py")
VARIANTS_FILE = Path("mtg-utils/src/mtg_utils/_card_ir/mirror/variants.py")
PIN_MENTION_FILES = (
    Path("CLAUDE.md"),
    Path("tests/mtg-utils/test_phase_wrapper.py"),
)
FIXTURES = Path("tests/fixtures")
POPULATION_FIXTURE = FIXTURES / "phase_variant_population.json"
BRIDGE_LEDGER_TEST = Path("tests/mtg-utils/test_bridge_ledger.py")
# A retirement canary guards a phase-misparse workaround that is NOT a ledger
# row (it suppresses a fire rather than recovering one, so no ADR-0048 gap
# retires it): it fails "<name>: RETIRE-READY — …" once the misparse is gone.
# Marked ``@pytest.mark.retirement_canary`` (registered in tests/conftest.py)
# and selected by marker, so a new canary needs no edit here.
CANARY_TESTS = Path("tests/mtg-utils")
CANARY_MARKER = "retirement_canary"


# ── pure pieces ─────────────────────────────────────────────────────────────────


def parse_effect_enum(rust_source: str) -> tuple[str, ...]:
    """The variant NAMES of ``pub enum Effect`` in phase's ``ability.rs``, in source
    order — names only, never the field shapes (the mirror infers those from the
    data). Skips ``//`` comments and ``#[...]`` attributes; a variant is an
    identifier at brace depth 0 followed by ``{``, ``(``, ``,`` or the closing
    brace."""
    m = re.search(r"pub enum Effect\s*\{", rust_source)
    if m is None:
        raise ValueError("no `pub enum Effect {` in the source")
    src = rust_source
    k = m.end()
    depth = 0
    names: list[str] = []
    while k < len(src):
        c = src[k]
        if src.startswith("//", k):
            k = src.find("\n", k)
            if k < 0:
                break
            continue
        if src.startswith("#[", k):
            d = 0
            while k < len(src):
                if src[k] == "[":
                    d += 1
                elif src[k] == "]":
                    d -= 1
                    if d == 0:
                        k += 1
                        break
                k += 1
            continue
        if c in "{(":
            depth += 1
        elif c in "})":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and c.isupper():
            ident = re.match(r"[A-Za-z_][A-Za-z0-9_]*", src[k:])
            assert ident is not None
            name = ident.group(0)
            rest = src[k + len(name) :].lstrip()
            if rest[:1] in ("{", "(", ",", "}"):
                names.append(name)
            k += len(name)
            continue
        k += 1
    if not names:
        raise ValueError("`pub enum Effect` parsed to zero variants")
    return tuple(names)


def rewrite_between_markers(text: str, begin: str, end: str, body: str) -> str:
    """Replace the lines strictly between the ``begin`` and ``end`` marker lines with
    ``body`` (which must end in a newline). Both markers must be present once."""
    b = text.index(begin)
    e = text.index(end, b)
    b_line_end = text.index("\n", b) + 1
    return text[:b_line_end] + body + text[e:]


def render_variants(names: Sequence[str]) -> str:
    lines = [f"    {json.dumps(n)},\n" for n in names]
    return "EFFECT_VARIANTS: tuple[str, ...] = (\n" + "".join(lines) + ")\n"


def render_zero_instance(names: Iterable[str]) -> str:
    lines = [f"        {json.dumps(n)},\n" for n in sorted(names)]
    return (
        "ZERO_INSTANCE_EFFECTS: frozenset[str] = frozenset(\n    {\n"
        + "".join(lines)
        + "    }\n)\n"
    )


# A LIVE pin site — the only tag mentions a bump rewrites — is the tag right
# after ``PHASE_TAG: str = "`` (the pin), ``PHASE_TAG == "`` (the pin test), or
# ``currently `` / ``currently ``\` (CLAUDE.md's "currently vX" mentions). Any
# other mention of the old tag is dated history ("the v0.66.0 pin bump found
# …") and must survive the bump untouched; a blanket replace rewrote those into
# falsehoods across three bumps.
_LIVE_PIN_PREFIX = r'(PHASE_TAG(?:: str)? ==? "|\bcurrently `?)'


def rewrite_pin(text: str, old_tag: str, new_tag: str) -> tuple[str, int]:
    """Rewrite ``old_tag`` at the live pin sites only (see ``_LIVE_PIN_PREFIX``);
    returns (text, count). A tag that merely extends ``old_tag`` (v0.94.0 vs
    v0.94.01) never matches."""
    rx = re.compile(_LIVE_PIN_PREFIX + re.escape(old_tag) + r"(?!\.?\d)")
    return rx.subn(lambda m: m.group(1) + new_tag, text)


def card_data_records(data: object) -> list[dict]:
    """card-data.json's records, whether the file is a name-keyed dict or a list."""
    if isinstance(data, dict):
        return [r for r in data.values() if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


@dataclass(frozen=True)
class ImpostorRow:
    oracle_id: str
    record_name: str
    record_text: str
    bulk_names: tuple[str, ...]  # the bulk card(s) carrying this oracle_id
    # The OTHER bulk card(s) whose face text this record's text is — non-empty
    # means a different card's text stamped with this oracle_id: a likely
    # impostor. Empty means no card carries the text: errata drift.
    text_owners: tuple[str, ...] = ()
    # The row is already in ``_phase._IMPOSTOR_RECORDS``: dropped at ingestion,
    # so it needs no decision — only a new likely impostor does.
    already_recorded: bool = False

    @property
    def likely_impostor(self) -> bool:
        return bool(self.text_owners)

    @property
    def needs_decision(self) -> bool:
        return self.likely_impostor and not self.already_recorded


def impostor_census(
    card_data: object,
    bulk_records: Iterable[Mapping],
    recorded: Iterable[tuple[str, str]] = (),
) -> list[ImpostorRow]:
    """card-data records whose ``oracle_text`` matches NO face text of the bulk card
    sharing their ``scryfall_oracle_id`` — the join phase's name-keyed corpus can
    get wrong (the Fast // Furious mis-join). Each row names ``text_owners``: the
    other oracle_ids whose face text the record's text IS (non-empty = a likely
    impostor; empty = errata drift), and whether its ``(oracle_id, text)`` is
    already one of the ``recorded`` impostor rows. Sorted: likely impostors
    needing a decision, then already-recorded ones, then errata drift.
    Report-only; never applied. Records whose oracle_id is absent from the bulk
    are not flagged (nothing to compare against)."""
    known = set(recorded)
    faces: dict[str, set[str]] = {}
    names: dict[str, set[str]] = {}
    owners: dict[str, set[str]] = {}  # normalized face text -> oracle_ids
    for rec in bulk_records:
        oid = rec.get("oracle_id") or ""
        if not oid:
            continue
        texts = faces.setdefault(oid, set())
        names.setdefault(oid, set()).add(rec.get("name") or "")
        face_texts = [rec.get("oracle_text")] + [
            f.get("oracle_text") for f in rec.get("card_faces") or []
        ]
        for t in face_texts:
            if t:
                texts.add(_norm(t))
                owners.setdefault(_norm(t), set()).add(oid)
    rows: list[ImpostorRow] = []
    for rec in card_data_records(card_data):
        oid = rec.get("scryfall_oracle_id") or ""
        text = rec.get("oracle_text") or ""
        if not oid or oid not in faces or not text:
            continue
        if _norm(text) not in faces[oid]:
            others = sorted(owners.get(_norm(text), set()) - {oid})
            rows.append(
                ImpostorRow(
                    oracle_id=oid,
                    record_name=rec.get("name") or "",
                    record_text=text,
                    bulk_names=tuple(sorted(names[oid])),
                    text_owners=tuple(
                        f"{n} ({o})" for o in others for n in sorted(names[o])
                    ),
                    already_recorded=(oid, text) in known,
                )
            )
    rows.sort(
        key=lambda r: (
            not r.needs_decision,
            not r.likely_impostor,
            r.record_name,
            r.oracle_id,
        )
    )
    return rows


def dead_impostor_rows(
    card_data: object, impostor_records: Iterable[tuple[str, str]]
) -> tuple[tuple[str, str], ...]:
    """The ``_phase._IMPOSTOR_RECORDS`` rows no RAW card-data record carries (a
    ``(oracle_id, exact text)`` row goes dead when upstream fixes or flips the
    join). Reads the raw records: the grouping seam drops impostors, so it cannot
    see them."""
    carried = {
        (r.get("scryfall_oracle_id") or "", r.get("oracle_text") or "")
        for r in card_data_records(card_data)
    }
    return tuple(sorted(row for row in impostor_records if row not in carried))


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


@dataclass(frozen=True)
class KeyDiff:
    key: str
    lost: tuple[str, ...]  # card names that lost this key
    gained: tuple[str, ...]  # card names that gained this key


def signal_diff(
    old_index: Mapping[str, Sequence[str]],
    new_index: Mapping[str, Sequence[str]],
    names_by_oid: Mapping[str, str],
) -> list[KeyDiff]:
    """Per signal KEY, the cards that lost / gained it between two signals indexes
    (``oracle_id -> idents``; an ident is ``key|scope|subject``). Only oracle_ids
    present in BOTH indexes count — a card that entered or left the pool is not a
    signal change. Sorted by keys with the most losses first."""
    lost: dict[str, set[str]] = {}
    gained: dict[str, set[str]] = {}
    for oid in old_index.keys() & new_index.keys():
        before = set(old_index[oid])
        after = set(new_index[oid])
        name = names_by_oid.get(oid, oid)
        for ident in before - after:
            lost.setdefault(ident.split("|", 1)[0], set()).add(name)
        for ident in after - before:
            gained.setdefault(ident.split("|", 1)[0], set()).add(name)
    out = [
        KeyDiff(
            key=k,
            lost=tuple(sorted(lost.get(k, ()))),
            gained=tuple(sorted(gained.get(k, ()))),
        )
        for k in lost.keys() | gained.keys()
    ]
    out.sort(key=lambda d: (-len(d.lost), -len(d.gained), d.key))
    return out


@dataclass(frozen=True)
class CardFacts:
    """What the triage needs to know about one card name the diff reports."""

    oracle_ids: tuple[str, ...]  # every bulk oracle_id with this name
    in_old_card_data: bool  # any of them had a phase record at the old tag
    in_new_card_data: bool  # …at the new tag

    def moved_between_variants(self, name: str, moved: Collection[str]) -> bool:
        """The key's change on this name is a signal moving to a sibling printing:
        several oracle_ids share the name, and the name both lost and gained the
        key (``moved``)."""
        return len(self.oracle_ids) > 1 and name in moved


class LossBucket(Enum):
    """A lost card's bucket, in priority order — the first that applies wins.
    The value is the report's display label."""

    PINNED = "PINNED — the test suite decides"
    DROPPED_UPSTREAM = "dropped upstream"
    VARIANT_CHURN = "variant churn"
    NEEDS_VERDICT = "needs verdict"

    @property
    def label(self) -> str:
        return self.value


# Collapsed to a count per key in the report: no human verdict needed.
COLLAPSED_BUCKETS = (LossBucket.DROPPED_UPSTREAM, LossBucket.VARIANT_CHURN)


def card_facts(
    names_by_oid: Mapping[str, str],
    old_card_data_oids: Iterable[str],
    new_card_data_oids: Iterable[str],
) -> dict[str, CardFacts]:
    """Per card NAME (the diff's unit), the facts :func:`classify_loss` and
    :func:`gain_needs_check` read."""
    old_cd, new_cd = set(old_card_data_oids), set(new_card_data_oids)
    by_name: dict[str, list[str]] = {}
    for oid, name in names_by_oid.items():
        by_name.setdefault(name, []).append(oid)
    return {
        name: CardFacts(
            oracle_ids=tuple(sorted(oids)),
            in_old_card_data=any(o in old_cd for o in oids),
            in_new_card_data=any(o in new_cd for o in oids),
        )
        for name, oids in by_name.items()
    }


def pinned_by(name: str, pins: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """The test sources pinning ``name`` — by full name or by any face of an
    ``A // B`` name (a test pins "Ajani, Nacatl Avenger", the diff reports the
    whole card)."""
    hits: set[str] = set()
    for n in (name, *name.split(" // ")):
        hits.update(pins.get(n, ()))
    return tuple(sorted(hits))


def classify_loss(
    name: str,
    facts: CardFacts | None,
    pins: Mapping[str, Sequence[str]],
    moved: Collection[str] = frozenset(),
) -> LossBucket:
    """A lost card's bucket, the first that applies: PINNED (a test, preset fixture
    or ledger pin names the card), DROPPED_UPSTREAM (a phase record at the old
    tag, none at the new), VARIANT_CHURN (:meth:`CardFacts.moved_between_variants`),
    else NEEDS_VERDICT."""
    if pinned_by(name, pins):
        return LossBucket.PINNED
    if facts is not None:
        if facts.in_old_card_data and not facts.in_new_card_data:
            return LossBucket.DROPPED_UPSTREAM
        if facts.moved_between_variants(name, moved):
            return LossBucket.VARIANT_CHURN
    return LossBucket.NEEDS_VERDICT


def gain_needs_check(
    name: str, facts: CardFacts | None, moved: Collection[str] = frozenset()
) -> bool:
    """True when a gain is on an already-parsed card — a phase record at both
    tags — unless the signal only moved between variants
    (:meth:`CardFacts.moved_between_variants`)."""
    return (
        facts is not None
        and facts.in_old_card_data
        and facts.in_new_card_data
        and not facts.moved_between_variants(name, moved)
    )


@dataclass(frozen=True)
class LossVerdict:
    """A loss the report can't settle: PINNED or NEEDS_VERDICT."""

    card: str
    key: str
    bucket: LossBucket
    sources: tuple[str, ...]  # the pinning test sources (PINNED only)
    residue_backed: bool


@dataclass(frozen=True)
class KeyTriage:
    """One key's diff, every loss and gain classified exactly once."""

    key: str
    lost: int
    gained: int
    verdicts: tuple[LossVerdict, ...]
    collapsed: Mapping[LossBucket, tuple[str, ...]]  # COLLAPSED_BUCKETS -> cards
    gains: tuple[tuple[str, bool], ...]  # (card, check?), checks first


def triage(
    diff: Sequence[KeyDiff],
    residue_backed: Mapping[str, Sequence[str]],
    facts: Mapping[str, CardFacts],
    pins: Mapping[str, Sequence[str]],
) -> list[KeyTriage]:
    """Classify every loss (:func:`classify_loss`) and gain
    (:func:`gain_needs_check`) of every key, in diff order."""
    out: list[KeyTriage] = []
    for d in diff:
        moved = set(d.lost) & set(d.gained)
        backed = set(residue_backed.get(d.key, ()))
        verdicts: list[LossVerdict] = []
        collapsed: dict[LossBucket, list[str]] = {b: [] for b in COLLAPSED_BUCKETS}
        for n in d.lost:
            bucket = classify_loss(n, facts.get(n), pins, moved)
            if bucket in collapsed:
                collapsed[bucket].append(n)
            else:
                verdicts.append(
                    LossVerdict(n, d.key, bucket, pinned_by(n, pins), n in backed)
                )
        gains = [(n, gain_needs_check(n, facts.get(n), moved)) for n in d.gained]
        gains.sort(key=lambda g: not g[1])
        out.append(
            KeyTriage(
                key=d.key,
                lost=len(d.lost),
                gained=len(d.gained),
                verdicts=tuple(verdicts),
                collapsed={b: tuple(ns) for b, ns in collapsed.items()},
                gains=tuple(gains),
            )
        )
    return out


@dataclass(frozen=True)
class BridgeReach:
    """One ledger row's corpus-wide reach: where it fires, and where only its
    gap holds (the row would fire if the text matched)."""

    bridge_id: str
    fires: int
    gap_hits: int
    gap_only_samples: tuple[str, ...]

    @property
    def gap_only(self) -> int:
        return self.gap_hits - self.fires


# A gap true on more than this share of the corpus gates on the ABSENCE of a
# structure (the usual shape: "no typed sacrifice node") or on a residue KIND
# that is everywhere; it retires when the pin grows that structure, so its
# gap-only cards are not sampled — the row gets one summary line instead.
NARROW_GAP_SHARE = 0.05


def bridge_reach(
    bridges: Mapping[str, Bridge],
    trees: Iterable[ConceptTree],
    *,
    samples: int = 5,
) -> list[BridgeReach]:
    """Evaluate every row's ``gap`` and ``match`` over ``trees`` (the corpus's
    signal trees, the shape bridges fire on in production). Rows keep ledger
    order."""
    fires = dict.fromkeys(bridges, 0)
    gap_hits = dict.fromkeys(bridges, 0)
    only: dict[str, list[str]] = {b: [] for b in bridges}
    for tree in trees:
        for bid, row in bridges.items():
            if not row.gap(tree):
                continue
            gap_hits[bid] += 1
            if row.match(tree):
                fires[bid] += 1
            elif len(only[bid]) < samples:
                only[bid].append(tree.name)
    return [BridgeReach(b, fires[b], gap_hits[b], tuple(only[b])) for b in bridges]


def dead_bridges(reach: Sequence[BridgeReach]) -> tuple[str, ...]:
    """Rows that fire on no card in the corpus: they serve nothing (a stale pin,
    or a gap/match pair that drifted apart) — a hard finding."""
    return tuple(r.bridge_id for r in reach if r.fires == 0)


def narrow_gap_breadth(reach: Sequence[BridgeReach], corpus: int) -> list[BridgeReach]:
    """Rows whose gap is NARROW (true on at most ``NARROW_GAP_SHARE`` of the
    corpus — a residue or hollow-static read) yet holds on cards the match
    doesn't, widest first. Informational: a gap-only card is usually a near miss
    (Phyrexian Vindicator beside the prevention row)."""
    rows = [r for r in reach if r.gap_only and r.gap_hits <= NARROW_GAP_SHARE * corpus]
    return sorted(rows, key=lambda r: -r.gap_only)


def wide_gaps(reach: Sequence[BridgeReach], corpus: int) -> list[BridgeReach]:
    """Rows whose gap holds on more than ``NARROW_GAP_SHARE`` of the corpus — an
    absence read — widest first. Summarised, never sampled, so no row is hidden."""
    rows = [r for r in reach if r.gap_hits > NARROW_GAP_SHARE * corpus]
    return sorted(rows, key=lambda r: -r.gap_hits)


RETIRE_READY = re.compile(r"^(?:FAILED\s+\S+::)?.*?(\w+): RETIRE-READY", re.MULTILINE)


def graduation_rows(pytest_output: str) -> tuple[str, ...]:
    """The names reported RETIRE-READY — bridge ids from ``test_bridge_ledger.py``
    (their gap closed) and workaround names from the retirement canaries (their
    misparse gone) — the graduation list a bump hands to the human."""
    ids = {m.group(1) for m in RETIRE_READY.finditer(pytest_output)}
    return tuple(sorted(ids))


# ── report sections: each returns its lines, render_report concatenates ─────────

GAINS_SHOWN = 25  # per key; the rest are counted


def render_rosters(
    variants_before: int, variants_after: int, zero_instance: Sequence[str]
) -> list[str]:
    return [
        "## Rosters",
        f"- EFFECT_VARIANTS: {variants_before} → {variants_after}",
        f"- ZERO_INSTANCE_EFFECTS: {len(zero_instance)} ({', '.join(zero_instance)})",
    ]


def render_census(
    census: Sequence[ImpostorRow], dead_impostors: Sequence[tuple[str, str]]
) -> list[str]:
    lines = ["## Impostor census (report only — never auto-applied)"]
    if census:
        n_imp = sum(r.likely_impostor for r in census)
        n_known = sum(r.likely_impostor and r.already_recorded for r in census)
        lines.append(
            f"- {len(census)} record(s) whose text matches no bulk face for their "
            f"oracle_id: {n_imp} LIKELY IMPOSTOR ({n_known} already recorded), "
            f"{len(census) - n_imp} errata drift."
        )
        for r in census:
            if not r.likely_impostor:
                verdict = "errata drift"
            elif r.already_recorded:
                verdict = (
                    "LIKELY IMPOSTOR, already in `_IMPOSTOR_RECORDS` — no decision "
                    f"needed; the text of {'; '.join(r.text_owners)}"
                )
            else:
                verdict = f"LIKELY IMPOSTOR — the text of {'; '.join(r.text_owners)}"
            lines.append(
                f"  - [{verdict}] `{r.oracle_id}` record {r.record_name!r} (bulk: "
                f"{', '.join(r.bulk_names)}): {r.record_text[:160]!r}"
            )
    else:
        lines.append("- none flagged")
    if dead_impostors:
        lines.extend(
            f"- DEAD `_IMPOSTOR_RECORDS` row: `{oid}` {text[:80]!r} — no record "
            "carries it"
            for oid, text in dead_impostors
        )
    else:
        lines.append("- every `_IMPOSTOR_RECORDS` row still matches a record")
    return lines


def render_signal_diff(triaged: Sequence[KeyTriage]) -> list[str]:
    lost = sum(t.lost for t in triaged)
    gained = sum(t.gained for t in triaged)
    lines = [
        "## Signal diff (per key; cards present in both indexes)",
        (
            f"- {lost} losses / {gained} gains across {len(triaged)} keys. Losses "
            f"are bucketed: {' / '.join(b.label for b in LossBucket)}; gains "
            "tagged [check] were on already-parsed cards."
        ),
    ]
    for t in triaged:
        lines.append(f"### {t.key}  (lost {t.lost}, gained {t.gained})")
        for v in t.verdicts:
            where = f" ({', '.join(v.sources)})" if v.sources else ""
            tag = "residue-backed → bridge candidate" if v.residue_backed else "silent"
            lines.append(f"- lost: {v.card}  [{v.bucket.label}{where}; {tag}]")
        for bucket, names in t.collapsed.items():
            if names:
                lines.append(
                    f"- lost ({bucket.label}): {len(names)}  <details><summary>cards"
                    f"</summary>{', '.join(names)}</details>"
                )
        for n, check in t.gains[:GAINS_SHOWN]:
            lines.append(f"- gained: {n}{'  [check]' if check else ''}")
        if len(t.gains) > GAINS_SHOWN:
            lines.append(f"- gained: … {len(t.gains) - GAINS_SHOWN} more")
    return lines


def render_needs_verdict(triaged: Sequence[KeyTriage]) -> list[str]:
    lines = ["## Needs a verdict (answer each in the bump's commit message)"]
    verdicts = sorted(
        (v for t in triaged for v in t.verdicts),
        key=lambda v: (v.bucket is not LossBucket.PINNED, v.key, v.card),
    )
    for v in verdicts:
        residue = ", residue-backed" if v.residue_backed else ""
        lines.append(f"- [{v.bucket.label}{residue}] {v.key}: {v.card}")
    return lines if verdicts else [*lines, "- none"]


def render_gains_to_check(triaged: Sequence[KeyTriage]) -> list[str]:
    lines = ["## Gains to check (already-parsed cards — false positive?)"]
    checks = [(t.key, n) for t in triaged for n, check in t.gains if check]
    lines.extend(f"- {key}: {n}" for key, n in sorted(checks, key=lambda c: c[0]))
    return lines if checks else [*lines, "- none"]


def render_graduation(graduation: Sequence[str]) -> list[str]:
    lines = ["## Graduation (RETIRE-READY bridges + retirement canaries)"]
    if graduation:
        return [*lines, *(f"- {b}" for b in graduation)]
    return [*lines, "- none — every bridge's gap and canary's misparse still hold"]


def render_bridge_reach(reach: Sequence[BridgeReach], corpus: int) -> list[str]:
    if not reach:
        return []
    lines = [f"## Bridge reach ({len(reach)} rows over {corpus} trees)"]
    dead = dead_bridges(reach)
    if dead:
        lines.extend(f"- DEAD — fires on no card: {b}" for b in dead)
    else:
        lines.append("- every row fires on at least one card")
    narrow = narrow_gap_breadth(reach, corpus)
    if narrow:
        lines.append(
            "- narrow gaps that also hold where the text doesn't match (informational):"
        )
        lines.extend(
            f"  - {r.bridge_id}: gap {r.gap_hits}, fires {r.fires} "
            f"(e.g. {', '.join(r.gap_only_samples)})"
            for r in narrow
        )
    wide = wide_gaps(reach, corpus)
    if wide:
        lines.append(
            "- wide gaps (absence reads, true on more than "
            f"{NARROW_GAP_SHARE:.0%} of the corpus; not sampled):"
        )
        lines.extend(
            f"  - {r.bridge_id}: gap {r.gap_hits}, fires {r.fires}" for r in wide
        )
    return lines


@dataclass
class ReportData:
    """Everything the report renders — the steps fill it in, :func:`render_report`
    reads it once."""

    old_tag: str
    new_tag: str
    notes: list[str] = field(default_factory=list)
    variants_before: int = 0
    variants_after: int = 0
    zero_instance: tuple[str, ...] = ()
    census: tuple[ImpostorRow, ...] = ()
    dead_impostors: tuple[tuple[str, str], ...] = ()
    diff: tuple[KeyDiff, ...] = ()
    residue_backed: Mapping[str, Sequence[str]] = field(default_factory=dict)
    facts: Mapping[str, CardFacts] = field(default_factory=dict)
    pins: Mapping[str, Sequence[str]] = field(default_factory=dict)
    graduation: tuple[str, ...] = ()
    reach: tuple[BridgeReach, ...] = ()
    corpus: int = 0


def render_report(data: ReportData) -> str:
    """The bump's triage report: one section per helper above, in the order a
    human works them (``docs/phase-pin-bump.md``)."""
    triaged = triage(data.diff, data.residue_backed, data.facts, data.pins)
    sections = [
        [f"# phase pin bump {data.old_tag} → {data.new_tag}"],
        render_rosters(data.variants_before, data.variants_after, data.zero_instance),
        render_census(data.census, data.dead_impostors),
        render_signal_diff(triaged),
        render_needs_verdict(triaged),
        render_gains_to_check(triaged),
        render_graduation(data.graduation),
        render_bridge_reach(data.reach, data.corpus),
        ["## Notes", *(f"- {n}" for n in data.notes)] if data.notes else [],
    ]
    return "\n\n".join("\n".join(s) for s in sections if s) + "\n"


# ── orchestration ───────────────────────────────────────────────────────────────

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]
Fetcher = Callable[[str], bytes]


@dataclass
class BumpContext:
    """Everything one bump run touches — repo root, tags, report dir, and the two
    external seams (subprocess runner, HTTP fetcher) a dry run replaces."""

    repo: Path
    old_tag: str
    new_tag: str
    report_dir: Path
    runner: Runner
    fetch: Fetcher
    card_data_path: Callable[[], Path]
    bulk_path: Path | None
    install_phase: bool = False
    report: ReportData = field(init=False)

    def __post_init__(self) -> None:
        self.report = ReportData(self.old_tag, self.new_tag)

    def old_card_data_path(self) -> Path:
        """The old tag's cached card-data, beside the new one (phase caches one
        file per tag) — absent when the old tag was never fetched here."""
        return self.card_data_path().with_name(f"card-data-{self.old_tag}.json")


def _read(ctx: BumpContext, rel: Path) -> str:
    return (ctx.repo / rel).read_text(encoding="utf-8")


def _write(ctx: BumpContext, rel: Path, text: str) -> None:
    (ctx.repo / rel).write_text(text, encoding="utf-8")


def step_pin(ctx: BumpContext) -> None:
    for rel in (PIN_FILE, *PIN_MENTION_FILES):
        text, n = rewrite_pin(_read(ctx, rel), ctx.old_tag, ctx.new_tag)
        if n == 0:
            raise RuntimeError(f"{rel}: the old tag {ctx.old_tag!r} does not appear")
        _write(ctx, rel, text)
        ctx.report.notes.append(f"{rel}: {n} tag mention(s) rewritten")
    _phase.PHASE_TAG = ctx.new_tag  # this process's own fetches read the attribute


def step_variants(ctx: BumpContext) -> None:
    url = f"{PHASE_RAW}/{ctx.new_tag}/{ABILITY_RS}"
    names = parse_effect_enum(ctx.fetch(url).decode("utf-8"))
    text = _read(ctx, VARIANTS_FILE)
    ctx.report.variants_before = len(parse_effect_enum_from_variants(text))
    text = rewrite_between_markers(
        text, VARIANTS_BEGIN, VARIANTS_END, render_variants(names)
    )
    _write(ctx, VARIANTS_FILE, text)
    ctx.report.variants_after = len(names)


def step_card_data(ctx: BumpContext) -> None:
    path = ctx.card_data_path()
    ctx.report.notes.append(f"card-data for {ctx.new_tag}: {path}")


def _run(ctx: BumpContext, *argv: str) -> str:
    proc = ctx.runner([sys.executable, "-m", *argv])
    if proc.returncode != 0:
        raise RuntimeError(f"`{' '.join(argv)}` failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout or ""


def step_substrate(ctx: BumpContext) -> None:
    _run(ctx, "mtg_utils.card_ir_substrate_build")
    population = json.loads(_read(ctx, POPULATION_FIXTURE))
    counts = population.get("population") or {}
    roster = parse_effect_enum_from_variants(_read(ctx, VARIANTS_FILE))
    zeros = tuple(n for n in roster if not counts.get(n))
    text = rewrite_between_markers(
        _read(ctx, VARIANTS_FILE), ZERO_BEGIN, ZERO_END, render_zero_instance(zeros)
    )
    _write(ctx, VARIANTS_FILE, text)
    ctx.report.zero_instance = tuple(sorted(zeros))


def parse_effect_enum_from_variants(variants_source: str) -> tuple[str, ...]:
    """The roster currently written between the EFFECT_VARIANTS markers."""
    b = variants_source.index(VARIANTS_BEGIN)
    e = variants_source.index(VARIANTS_END, b)
    block = variants_source[b:e]
    return tuple(re.findall(r'^    "([A-Za-z0-9_]+)",$', block, re.MULTILINE))


def _bulk_records(ctx: BumpContext) -> list[dict]:
    from mtg_utils.card_pool import CardPool

    return CardPool.load(ctx.bulk_path).cards


def step_impostor_census(ctx: BumpContext) -> None:
    card_data = json.loads(ctx.card_data_path().read_text(encoding="utf-8"))
    # The table the census exists to maintain — read, never written, here.
    rows = _phase._IMPOSTOR_RECORDS  # noqa: SLF001
    ctx.report.census = tuple(impostor_census(card_data, _bulk_records(ctx), rows))
    ctx.report.dead_impostors = dead_impostor_rows(card_data, rows)


def _card_data_oids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        r["scryfall_oracle_id"]
        for r in card_data_records(data)
        if r.get("scryfall_oracle_id")
    }


def _signals_pkl(ctx: BumpContext) -> Path | None:
    from mtg_utils._analysis.signals_index import _sidecar_path
    from mtg_utils.bulk_loader import default_bulk_path

    bulk = ctx.bulk_path or default_bulk_path()
    return _sidecar_path(bulk) if bulk is not None else None


def step_rebuild(ctx: BumpContext) -> None:
    pkl = _signals_pkl(ctx)
    old_copy = ctx.report_dir / f"signals-{ctx.old_tag}.pkl"
    if old_copy.exists():
        # A resume at this step: the index on disk is already the rebuilt one, so
        # the copy the first run took is the only pre-bump baseline there is.
        ctx.report.notes.append(f"old signals index already copied to {ctx.report_dir}")
    elif pkl is not None and pkl.exists():
        ctx.report_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pkl, old_copy)
        ctx.report.notes.append(f"old signals index copied to {ctx.report_dir}")
    else:
        ctx.report.notes.append(
            "no prior signals index found — the signal diff is skipped"
        )
    snapshot = _run(ctx, "mtg_utils.build_card_snapshot").strip()
    if snapshot:
        # Unresolved names and text-only cards are coverage holes to triage.
        ctx.report.notes.append(f"card snapshot: {snapshot}")
    _run(ctx, "mtg_utils.card_ir_crosswalk_build")
    _run(ctx, "mtg_utils.signals_index_build")
    if ctx.install_phase:
        _phase.install_phase()  # moves the cached clone to the (already set) new tag
        ctx.report.notes.append("phase clone moved to the new tag and rebuilt")


def _load_index(path: Path) -> dict[str, tuple[str, ...]]:
    with path.open("rb") as f:
        payload = pickle.load(f)
    return payload.get("index") or payload.get("cards") or {}


def step_signal_diff(ctx: BumpContext) -> None:
    old_pkl = ctx.report_dir / f"signals-{ctx.old_tag}.pkl"
    new_pkl = _signals_pkl(ctx)
    if not old_pkl.exists() or new_pkl is None or not new_pkl.exists():
        return
    bulk = _bulk_records(ctx)
    names = {r["oracle_id"]: r.get("name", "") for r in bulk if r.get("oracle_id")}
    diff = signal_diff(_load_index(old_pkl), _load_index(new_pkl), names)
    ctx.report.diff = tuple(diff)
    ctx.report.facts = card_facts(
        names,
        _card_data_oids(ctx.old_card_data_path()),
        _card_data_oids(ctx.card_data_path()),
    )
    from mtg_utils.build_card_snapshot import scan_test_usage

    ctx.report.pins = scan_test_usage(ctx.repo)
    # Which losses still have a residue the tree carries? Those are bridge material.
    by_name = {r.get("name", ""): r for r in bulk if r.get("oracle_id")}
    backed: dict[str, tuple[str, ...]] = {}
    for d in diff:
        hits = []
        for n in d.lost:
            rec = by_name.get(n)
            if rec and any(t.has_residue() for t in _corpus_trees(rec)):
                hits.append(n)
        if hits:
            backed[d.key] = tuple(hits)
    ctx.report.residue_backed = backed


def _corpus_trees(rec: dict) -> tuple:
    """A bulk record's trees as production fires bridges on them: the signal
    trees with the bulk threaded (so a phase-missing face gets its W2c text-only
    tree) and ``text_only_fallback`` on, which serves phase's trees when it covers
    the card and full text-only trees only for a wholly phase-uncovered folded
    object (ADR-0025) — the reach of every missing_face row."""
    from mtg_utils._analysis.signal_trees import signal_trees_for

    return signal_trees_for(rec, bulk=rec, text_only_fallback=True)


def step_graduation(ctx: BumpContext) -> None:
    # Two runs, because ``-m`` filters every collected item: the whole ledger
    # file, then only the marker-selected canaries. Their outputs are read as one.
    pytest = [sys.executable, "-m", "pytest", "-q"]
    out = ""
    for argv in (
        [*pytest, str(ctx.repo / BRIDGE_LEDGER_TEST)],
        [*pytest, str(ctx.repo / CANARY_TESTS), "-m", CANARY_MARKER],
    ):
        proc = ctx.runner(argv)
        out += (proc.stdout or "") + (proc.stderr or "")
    ctx.report.graduation = graduation_rows(out)
    # Every row's corpus reach: a row that fires nowhere, or a narrow gap that
    # outruns its match, is a retirement that won't read RETIRE-READY.
    from mtg_utils._analysis.bridge_ledger import BRIDGES

    started = time.monotonic()
    seen: set[str] = set()
    trees: list = []
    for rec in _bulk_records(ctx):
        oid = rec.get("oracle_id")
        if oid and oid not in seen:
            seen.add(oid)
            trees.extend(_corpus_trees(rec))
    ctx.report.reach = tuple(bridge_reach(BRIDGES, trees))
    ctx.report.corpus = len(trees)
    ctx.report.notes.append(
        f"bridge reach: {len(BRIDGES)} rows over {len(trees)} trees in "
        f"{time.monotonic() - started:.1f}s"
    )


STEPS: tuple[tuple[str, Callable[[BumpContext], None]], ...] = (
    ("pin", step_pin),
    ("variants", step_variants),
    ("card-data", step_card_data),
    ("substrate", step_substrate),
    ("impostor-census", step_impostor_census),
    ("rebuild", step_rebuild),
    ("signal-diff", step_signal_diff),
    ("graduation", step_graduation),
)


OLD_TAG_MARKER = "old-tag"


def resume_old_tag(report_dir: Path) -> str:
    """The tag an interrupted bump under *report_dir* started from. Step 1 rewrites
    ``PHASE_TAG`` on disk, so by the time ``--from-step`` runs the module's pin IS
    the new tag; the marker ``run`` wrote before step 1 is the only record of the
    old one (and what the signal diff's "old index" copy is named after)."""
    marker = report_dir / OLD_TAG_MARKER
    try:
        tag = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise click.ClickException(
            f"no interrupted bump to resume under {report_dir} ({marker.name} missing)"
        ) from exc
    if not tag:
        raise click.ClickException(f"{marker} is empty — no old tag to resume from")
    return tag


def run(ctx: BumpContext, *, from_step: int = 1, echo: Callable[[str], None]) -> Path:
    """Run the steps from ``from_step`` (1-based); write and return the report."""
    if from_step == 1:
        ctx.report_dir.mkdir(parents=True, exist_ok=True)
        (ctx.report_dir / OLD_TAG_MARKER).write_text(
            ctx.old_tag + "\n", encoding="utf-8"
        )
    for i, (name, fn) in enumerate(STEPS, start=1):
        if i < from_step:
            continue
        echo(f"[{i}/{len(STEPS)}] {name}")
        fn(ctx)
    ctx.report_dir.mkdir(parents=True, exist_ok=True)
    report = ctx.report_dir / "report.md"
    report.write_text(render_report(ctx.report), encoding="utf-8")
    return report


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_report_dir(tag: str) -> Path:
    return _phase.cache_dir().parent / "phase-bump" / tag


def _fetch(url: str) -> bytes:
    from mtg_utils._http import urllib_get

    return urllib_get(url, user_agent="mtg-skills/bump-phase-pin")


def _subprocess_runner(argv: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


@click.command()
@click.argument("tag")
@click.option("--from-step", type=click.IntRange(1, len(STEPS)), default=1)
@click.option("--install-phase", is_flag=True, help="Also move the phase clone.")
@bulk_data_option
def main(
    tag: str, from_step: int, bulk_data: Path | None, *, install_phase: bool
) -> None:
    """Bump the phase-rs pin to TAG: edit, regenerate, report (never CI)."""
    report_dir = _default_report_dir(tag)
    if from_step > 1:
        old_tag = resume_old_tag(report_dir)
    else:
        old_tag = _phase.PHASE_TAG
        if old_tag == tag:
            raise click.ClickException(
                f"the phase pin is already {tag}: resume an interrupted bump with "
                f"--from-step N (its report dir is {report_dir}), or restore "
                "PHASE_TAG and the generated rosters (git checkout) to start over"
            )
    ctx = BumpContext(
        repo=_repo_root(),
        old_tag=old_tag,
        new_tag=tag,
        report_dir=report_dir,
        runner=_subprocess_runner,
        fetch=_fetch,
        card_data_path=_phase.ensure_card_data,
        bulk_path=bulk_data,
        install_phase=install_phase,
    )
    if from_step > 1:
        _phase.PHASE_TAG = tag
    report = run(ctx, from_step=from_step, echo=lambda s: click.echo(s, err=True))
    click.echo(str(report))


if __name__ == "__main__":  # pragma: no cover
    main()
