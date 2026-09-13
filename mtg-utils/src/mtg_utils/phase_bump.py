"""``bump-phase-pin <tag>`` — the scripted phase-rs pin bump (ADR-0028's validated
spike, ADR-0049).

A pin bump used to be a ~47-file change with three steps that lived only in a memory
note (the crosswalk fixture had no writer, the impostor census and the corpus signal
diff were re-derived by hand). This CLI runs the whole recipe in order and stops at
the first failure; ``--from-step N`` resumes. Every judgment call stays human: the
script edits the pin and the generated rosters, regenerates every artifact that has a
builder, and writes ONE markdown report — the impostor census, the per-key signal
diff (lost idents split into residue-backed, i.e. bridgeable, vs silent), and the
ledger's RETIRE-READY rows — for the triage that follows.

Steps:
  1 pin                 PHASE_TAG, the CLAUDE.md mentions, the pin test
  2 variants            EFFECT_VARIANTS from phase's ``ability.rs`` at the tag
  3 card-data           fetch + cache card-data.json for the tag
  4 substrate           build-card-ir-substrate; ZERO_INSTANCE_EFFECTS from the zeros
  5 crosswalk-fixture   rewrite tests/fixtures/crosswalk_fixture_cards.json
  6 impostor-census     card-data records whose text matches no bulk face
  7 rebuild             copy the signals .pkl aside; snapshot, sidecar, signals index
  8 signal-diff         old vs new signals index, per key
  9 graduation          test_bridge_ledger.py RETIRE-READY rows

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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import click

from mtg_utils import _phase

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
CROSSWALK_FIXTURE = FIXTURES / "crosswalk_fixture_cards.json"
POPULATION_FIXTURE = FIXTURES / "phase_variant_population.json"
BRIDGE_LEDGER_TEST = Path("tests/mtg-utils/test_bridge_ledger.py")


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


def rewrite_pin(text: str, old_tag: str, new_tag: str) -> tuple[str, int]:
    """Replace every exact ``old_tag`` occurrence; returns (text, count)."""
    return text.replace(old_tag, new_tag), text.count(old_tag)


def card_data_records(data: object) -> list[dict]:
    """card-data.json's records, whether the file is a name-keyed dict or a list."""
    if isinstance(data, dict):
        return [r for r in data.values() if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return []


def regen_crosswalk_fixture(
    fixture: dict, card_data: object, new_tag: str
) -> tuple[dict, list[str]]:
    """Rewrite each ``cards`` entry (a raw phase face record keyed by the bulk pin
    name) with the same card's record from the new card-data — matched by the
    record's ``scryfall_oracle_id`` AND casefolded name, so a renamed or re-keyed
    record never silently swaps in a different card. ``scryfall_keywords`` and
    ``text_only_faces`` are kept verbatim (they come from the bulk, not phase).
    Returns the new fixture and the names that had NO matching record (kept as
    they were, and reported — a coverage hole to triage, never a silent drop)."""
    by_key: dict[tuple[str, str], dict] = {}
    for rec in card_data_records(card_data):
        oid = rec.get("scryfall_oracle_id") or ""
        nm = (rec.get("name") or "").casefold()
        if oid and nm:
            by_key.setdefault((oid, nm), rec)  # first record wins, deterministic
    out_cards: dict[str, dict] = {}
    missing: list[str] = []
    for pin_name, old in fixture["cards"].items():
        key = (old.get("scryfall_oracle_id") or "", (old.get("name") or "").casefold())
        new = by_key.get(key)
        if new is None:
            missing.append(pin_name)
            out_cards[pin_name] = old
        else:
            out_cards[pin_name] = new
    new_fixture = dict(fixture)
    new_fixture["phase_tag"] = new_tag
    new_fixture["cards"] = out_cards
    return new_fixture, missing


@dataclass(frozen=True)
class ImpostorRow:
    oracle_id: str
    record_name: str
    record_text: str
    bulk_names: tuple[str, ...]  # the bulk card(s) carrying this oracle_id


def impostor_census(
    card_data: object, bulk_records: Iterable[Mapping]
) -> list[ImpostorRow]:
    """card-data records whose ``oracle_text`` matches NO face text of the bulk card
    sharing their ``scryfall_oracle_id`` — the join phase's name-keyed corpus can
    get wrong (the Fast // Furious mis-join). Report-only: the v0.23.0 census found
    8 errata-drift false positives, so a human decides what enters
    ``_phase._IMPOSTOR_RECORDS``. Records whose oracle_id is absent from the bulk
    are not flagged (nothing to compare against)."""
    faces: dict[str, set[str]] = {}
    names: dict[str, set[str]] = {}
    for rec in bulk_records:
        oid = rec.get("oracle_id") or ""
        if not oid:
            continue
        texts = faces.setdefault(oid, set())
        names.setdefault(oid, set()).add(rec.get("name") or "")
        if rec.get("oracle_text"):
            texts.add(_norm(rec["oracle_text"]))
        for face in rec.get("card_faces") or []:
            if face.get("oracle_text"):
                texts.add(_norm(face["oracle_text"]))
    rows: list[ImpostorRow] = []
    for rec in card_data_records(card_data):
        oid = rec.get("scryfall_oracle_id") or ""
        text = rec.get("oracle_text") or ""
        if not oid or oid not in faces or not text:
            continue
        if _norm(text) not in faces[oid]:
            rows.append(
                ImpostorRow(
                    oracle_id=oid,
                    record_name=rec.get("name") or "",
                    record_text=text,
                    bulk_names=tuple(sorted(names[oid])),
                )
            )
    rows.sort(key=lambda r: (r.record_name, r.oracle_id))
    return rows


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


RETIRE_READY = re.compile(r"^(?:FAILED\s+\S+::)?.*?(\w+): RETIRE-READY", re.MULTILINE)


def graduation_rows(pytest_output: str) -> tuple[str, ...]:
    """The bridge ids ``test_bridge_ledger.py`` reports RETIRE-READY (their gap
    closed) — the graduation list a bump hands to the human."""
    ids = {m.group(1) for m in RETIRE_READY.finditer(pytest_output)}
    return tuple(sorted(ids))


def render_report(
    *,
    old_tag: str,
    new_tag: str,
    variants_before: int,
    variants_after: int,
    zero_instance: Sequence[str],
    fixture_missing: Sequence[str],
    census: Sequence[ImpostorRow],
    diff: Sequence[KeyDiff],
    residue_backed: Mapping[str, Sequence[str]],
    graduation: Sequence[str],
    notes: Sequence[str],
) -> str:
    lines = [
        f"# phase pin bump {old_tag} → {new_tag}",
        "",
        "## Rosters",
        f"- EFFECT_VARIANTS: {variants_before} → {variants_after}",
        f"- ZERO_INSTANCE_EFFECTS: {len(zero_instance)} ({', '.join(zero_instance)})",
        "",
        "## Crosswalk fixture",
    ]
    if fixture_missing:
        lines.append(
            f"- {len(fixture_missing)} pinned card(s) have NO record at {new_tag} "
            "(old record kept; a coverage hole to triage):"
        )
        lines.extend(f"  - {n}" for n in fixture_missing)
    else:
        lines.append("- every pinned card re-resolved")
    lines += ["", "## Impostor census (report only — never auto-applied)"]
    if census:
        lines.append(
            f"- {len(census)} record(s) whose text matches no bulk face for their "
            "oracle_id. Errata drift is NOT an impostor; a different card's text is."
        )
        for r in census:
            lines.append(
                f"  - `{r.oracle_id}` record {r.record_name!r} (bulk: "
                f"{', '.join(r.bulk_names)}): {r.record_text[:160]!r}"
            )
    else:
        lines.append("- none flagged")
    lines += ["", "## Signal diff (per key; cards present in both indexes)"]
    total_lost = sum(len(d.lost) for d in diff)
    total_gained = sum(len(d.gained) for d in diff)
    lines.append(
        f"- {total_lost} losses / {total_gained} gains across {len(diff)} keys"
    )
    for d in diff:
        lines.append(f"### {d.key}  (lost {len(d.lost)}, gained {len(d.gained)})")
        if d.lost:
            backed = set(residue_backed.get(d.key, ()))
            for n in d.lost:
                tag = "residue-backed → bridge candidate" if n in backed else "silent"
                lines.append(f"- lost: {n}  [{tag}]")
        for n in d.gained[:25]:
            lines.append(f"- gained: {n}")
        if len(d.gained) > 25:
            lines.append(f"- gained: … {len(d.gained) - 25} more")
    lines += ["", "## Bridge graduation (RETIRE-READY rows)"]
    if graduation:
        lines.extend(f"- {b}" for b in graduation)
    else:
        lines.append("- none — every bridge's gap still holds")
    if notes:
        lines += ["", "## Notes", *[f"- {n}" for n in notes]]
    return "\n".join(lines) + "\n"


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
    notes: list[str] = field(default_factory=list)
    variants_before: int = 0
    variants_after: int = 0
    zero_instance: tuple[str, ...] = ()
    fixture_missing: tuple[str, ...] = ()
    census: tuple[ImpostorRow, ...] = ()
    diff: tuple[KeyDiff, ...] = ()
    residue_backed: dict[str, tuple[str, ...]] = field(default_factory=dict)
    graduation: tuple[str, ...] = ()


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
        ctx.notes.append(f"{rel}: {n} tag mention(s) rewritten")
    _phase.PHASE_TAG = ctx.new_tag  # this process's own fetches read the attribute


def step_variants(ctx: BumpContext) -> None:
    url = f"{PHASE_RAW}/{ctx.new_tag}/{ABILITY_RS}"
    names = parse_effect_enum(ctx.fetch(url).decode("utf-8"))
    text = _read(ctx, VARIANTS_FILE)
    ctx.variants_before = len(parse_effect_enum_from_variants(text))
    text = rewrite_between_markers(
        text, VARIANTS_BEGIN, VARIANTS_END, render_variants(names)
    )
    _write(ctx, VARIANTS_FILE, text)
    ctx.variants_after = len(names)


def step_card_data(ctx: BumpContext) -> None:
    path = ctx.card_data_path()
    ctx.notes.append(f"card-data for {ctx.new_tag}: {path}")


def _run(ctx: BumpContext, *argv: str) -> None:
    proc = ctx.runner([sys.executable, "-m", *argv])
    if proc.returncode != 0:
        raise RuntimeError(f"`{' '.join(argv)}` failed:\n{proc.stdout}\n{proc.stderr}")


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
    ctx.zero_instance = tuple(sorted(zeros))


def parse_effect_enum_from_variants(variants_source: str) -> tuple[str, ...]:
    """The roster currently written between the EFFECT_VARIANTS markers."""
    b = variants_source.index(VARIANTS_BEGIN)
    e = variants_source.index(VARIANTS_END, b)
    block = variants_source[b:e]
    return tuple(re.findall(r'^    "([A-Za-z0-9_]+)",$', block, re.MULTILINE))


def step_crosswalk_fixture(ctx: BumpContext) -> None:
    fixture = json.loads(_read(ctx, CROSSWALK_FIXTURE))
    card_data = json.loads(ctx.card_data_path().read_text(encoding="utf-8"))
    new_fixture, missing = regen_crosswalk_fixture(fixture, card_data, ctx.new_tag)
    _write(
        ctx,
        CROSSWALK_FIXTURE,
        json.dumps(new_fixture, indent=1, ensure_ascii=False) + "\n",
    )
    ctx.fixture_missing = tuple(missing)


def _bulk_records(ctx: BumpContext) -> list[dict]:
    from mtg_utils.card_pool import CardPool

    return CardPool.load(ctx.bulk_path).cards


def step_impostor_census(ctx: BumpContext) -> None:
    card_data = json.loads(ctx.card_data_path().read_text(encoding="utf-8"))
    ctx.census = tuple(impostor_census(card_data, _bulk_records(ctx)))


def _signals_pkl(ctx: BumpContext) -> Path | None:
    from mtg_utils._deck_forge.signals_index import _sidecar_path
    from mtg_utils.bulk_loader import default_bulk_path

    bulk = ctx.bulk_path or default_bulk_path()
    return _sidecar_path(bulk) if bulk is not None else None


def step_rebuild(ctx: BumpContext) -> None:
    pkl = _signals_pkl(ctx)
    if pkl is not None and pkl.exists():
        ctx.report_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pkl, ctx.report_dir / f"signals-{ctx.old_tag}.pkl")
        ctx.notes.append(f"old signals index copied to {ctx.report_dir}")
    else:
        ctx.notes.append("no prior signals index found — the signal diff is skipped")
    _run(ctx, "mtg_utils.build_card_snapshot")
    _run(ctx, "mtg_utils.card_ir_crosswalk_build")
    _run(ctx, "mtg_utils.signals_index_build")
    if ctx.install_phase:
        _phase.install_phase()  # moves the cached clone to the (already set) new tag
        ctx.notes.append("phase clone moved to the new tag and rebuilt")


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
    ctx.diff = tuple(diff)
    # Which losses still have a residue the tree carries? Those are bridge material.
    from mtg_utils._card_ir.trees import trees_for

    by_name = {r.get("name", ""): r for r in bulk if r.get("oracle_id")}
    backed: dict[str, tuple[str, ...]] = {}
    for d in diff:
        hits = []
        for n in d.lost:
            rec = by_name.get(n)
            if rec and any(t.has_residue() for t in trees_for(rec)):
                hits.append(n)
        if hits:
            backed[d.key] = tuple(hits)
    ctx.residue_backed = backed


def step_graduation(ctx: BumpContext) -> None:
    proc = ctx.runner(
        [sys.executable, "-m", "pytest", str(ctx.repo / BRIDGE_LEDGER_TEST), "-q"]
    )
    ctx.graduation = graduation_rows((proc.stdout or "") + (proc.stderr or ""))


STEPS: tuple[tuple[str, Callable[[BumpContext], None]], ...] = (
    ("pin", step_pin),
    ("variants", step_variants),
    ("card-data", step_card_data),
    ("substrate", step_substrate),
    ("crosswalk-fixture", step_crosswalk_fixture),
    ("impostor-census", step_impostor_census),
    ("rebuild", step_rebuild),
    ("signal-diff", step_signal_diff),
    ("graduation", step_graduation),
)


def run(ctx: BumpContext, *, from_step: int = 1, echo: Callable[[str], None]) -> Path:
    """Run the steps from ``from_step`` (1-based); write and return the report."""
    for i, (name, fn) in enumerate(STEPS, start=1):
        if i < from_step:
            continue
        echo(f"[{i}/{len(STEPS)}] {name}")
        fn(ctx)
    ctx.report_dir.mkdir(parents=True, exist_ok=True)
    report = ctx.report_dir / "report.md"
    report.write_text(
        render_report(
            old_tag=ctx.old_tag,
            new_tag=ctx.new_tag,
            variants_before=ctx.variants_before,
            variants_after=ctx.variants_after,
            zero_instance=ctx.zero_instance,
            fixture_missing=ctx.fixture_missing,
            census=ctx.census,
            diff=ctx.diff,
            residue_backed=ctx.residue_backed,
            graduation=ctx.graduation,
            notes=ctx.notes,
        ),
        encoding="utf-8",
    )
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
@click.option("--bulk-data", type=click.Path(exists=True, path_type=Path), default=None)
def main(
    tag: str, from_step: int, bulk_data: Path | None, *, install_phase: bool
) -> None:
    """Bump the phase-rs pin to TAG: edit, regenerate, report (never CI)."""
    ctx = BumpContext(
        repo=_repo_root(),
        old_tag=_phase.PHASE_TAG,
        new_tag=tag,
        report_dir=_default_report_dir(tag),
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
